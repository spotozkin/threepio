"""Voice activity detection using webrtcvad and energy-based fallback."""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque
from queue import Queue, Full, Empty
from typing import Callable, Literal, Sequence

logger = logging.getLogger(__name__)

# webrtcvad frame must be 10, 20, or 30 ms at 8/16/32 kHz
VAD_FRAME_MS = 30
VAD_SAMPLE_RATE = 16000
VAD_BYTES_PER_FRAME = int(VAD_SAMPLE_RATE * VAD_FRAME_MS / 1000) * 2  # 960 for 30ms @ 16kHz

# Energy fallback: thresholds (normalized RMS 0..1); start > end for hysteresis
def _energy_start_threshold() -> float:
    v = os.environ.get("THREEPIO_ENERGY_START", "0.005").strip()
    try:
        return max(0.0, float(v))
    except ValueError:
        return 0.005


def _energy_end_threshold() -> float:
    v = os.environ.get("THREEPIO_ENERGY_END", "0.003").strip()
    try:
        return max(0.0, float(v))
    except ValueError:
        return 0.003


# Speaking-phase thresholds and timing (avoid self-trigger from TTS playback)
def get_energy_start_speaking() -> float:
    v = os.environ.get("THREEPIO_ENERGY_START_SPEAKING", "0.030").strip()
    try:
        return max(0.0, float(v))
    except ValueError:
        return 0.030


def get_energy_end_speaking() -> float:
    v = os.environ.get("THREEPIO_ENERGY_END_SPEAKING", "0.020").strip()
    try:
        return max(0.0, float(v))
    except ValueError:
        return 0.020


def get_speech_suppress_ms() -> int:
    """Suppression window (ms) after playback start during which barge-in is ignored. Default 2000."""
    v = os.environ.get("THREEPIO_SPEECH_SUPPRESS_MS", "2000").strip()
    try:
        return max(0, int(v))
    except ValueError:
        return 2000


def is_speaking_suppression_active(
    now: float, speaking_start_ts: float | None, suppress_ms: int
) -> bool:
    """True if within the post-playback-start suppression window (barge-in and VAD finalization suppressed)."""
    if speaking_start_ts is None or suppress_ms <= 0:
        return False
    return (now - speaking_start_ts) * 1000 < suppress_ms


def get_post_speech_cooldown_ms() -> int:
    v = os.environ.get("THREEPIO_POST_SPEECH_COOLDOWN_MS", "250").strip()
    try:
        return max(0, int(v))
    except ValueError:
        return 250


def get_vad_start_rms() -> float:
    """RMS threshold for allowing VAD speech_start (gate reduces false triggers)."""
    v = os.environ.get("THREEPIO_VAD_START_RMS", "0.004").strip()
    try:
        return max(0.0, float(v))
    except ValueError:
        return 0.004


def get_vad_cooldown_ms() -> int:
    """Cooldown (ms) after rejected utterance (too short / no speech) before accepting speech_start again."""
    v = os.environ.get("THREEPIO_VAD_COOLDOWN_MS", "400").strip()
    try:
        return max(0, int(v))
    except ValueError:
        return 400


def vad_speech_start_allowed(
    vad_start: bool, energy_start: bool, rms: float, rms_threshold: float
) -> bool:
    """True if speech_start (vad or energy) is allowed: both detected and RMS >= threshold."""
    if not (vad_start or energy_start):
        return False
    return rms >= rms_threshold


def should_accept_speech(
    is_vad_speech: bool,
    rms: float,
    now_ms: int,
    last_reject_ms: int,
    start_rms: float,
    cooldown_ms: int,
) -> bool:
    """
    Pure predicate: True if speech_start should be accepted.
    - is_vad_speech: VAD or energy detected speech.
    - rms, start_rms: RMS gate (rms >= start_rms).
    - now_ms, last_reject_ms: timestamps in ms; last_reject_ms=0 means no prior reject.
    - cooldown_ms: ignore new speech_start for this many ms after last_reject_ms.
    """
    if not is_vad_speech or rms < start_rms:
        return False
    if last_reject_ms == 0:
        return True
    if cooldown_ms <= 0:
        return True
    return (now_ms - last_reject_ms) >= cooldown_ms


def get_bargein_confirm_ms() -> int:
    v = os.environ.get("THREEPIO_BARGEIN_CONFIRM_MS", "450").strip()
    try:
        return max(0, int(v))
    except ValueError:
        return 450


def get_bargein_sustained_frames() -> int:
    """Number of consecutive speech frames required before accepting barge-in (e.g. 10 = 300ms). Default 10."""
    v = os.environ.get("THREEPIO_BARGEIN_SUSTAINED_FRAMES", "10").strip()
    try:
        return max(1, int(v))
    except ValueError:
        return 10


def get_bargein_rms_multiplier() -> float:
    """Require current RMS >= (VAD_START_RMS * this) to accept barge-in. Default 2.0."""
    v = os.environ.get("THREEPIO_BARGEIN_RMS_MULTIPLIER", "2.0").strip()
    try:
        return max(0.5, float(v))
    except ValueError:
        return 2.0


def energy_bargein_confirmed(rms_recent: Sequence[float], confirm_frames: int) -> bool:
    """True if RMS has been above ENERGY_START_SPEAKING for at least confirm_frames consecutive frames."""
    if confirm_frames < 1 or len(rms_recent) < confirm_frames:
        return False
    th = get_energy_start_speaking()
    tail = list(rms_recent)[-confirm_frames:]
    return all(r >= th for r in tail)


def energy_speech_start(rms_recent: Sequence[float], n_frames: int = 3) -> bool:
    """True if the last n_frames all have RMS > THREEPIO_ENERGY_START (default 0.005)."""
    if len(rms_recent) < n_frames:
        return False
    th = _energy_start_threshold()
    for r in list(rms_recent)[-n_frames:]:
        if r <= th:
            return False
    return True


def energy_speech_end(rms_recent: Sequence[float], silence_frames: int) -> bool:
    """True if the last silence_frames all have RMS < THREEPIO_ENERGY_END (default 0.003)."""
    if silence_frames < 1 or len(rms_recent) < silence_frames:
        return False
    th = _energy_end_threshold()
    for r in list(rms_recent)[-silence_frames:]:
        if r >= th:
            return False
    return True


def _debug_enabled() -> bool:
    v = os.environ.get("THREEPIO_DEBUG", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _vad_aggressiveness() -> int:
    """THREEPIO_VAD_AGGR: 0-3, default 2."""
    v = os.environ.get("THREEPIO_VAD_AGGR", "2").strip()
    try:
        agg = int(v)
        return max(0, min(3, agg))
    except ValueError:
        return 2


def _get_vad():
    """Lazy webrtcvad instance."""
    try:
        import webrtcvad
    except ImportError as e:
        raise RuntimeError(
            "webrtcvad not installed. pip install webrtcvad"
        ) from e
    return webrtcvad.Vad(_vad_aggressiveness())


def _count_consecutive_speech_frames_from_tail(
    frames: Sequence[bytes], rms_list: Sequence[float], energy_th: float
) -> int:
    """Count consecutive frames from the end that are speech (VAD or RMS >= energy_th). Returns 0 if not enough data."""
    if not frames or not rms_list or len(frames) != len(rms_list):
        return 0
    try:
        vad = _get_vad()
    except RuntimeError:
        vad = None
    n = len(frames)
    count = 0
    for i in range(n - 1, -1, -1):
        frame = frames[i]
        rms = rms_list[i] if i < len(rms_list) else 0.0
        is_speech = rms >= energy_th
        if not is_speech and vad is not None and len(frame) >= VAD_BYTES_PER_FRAME:
            chunk = frame[:VAD_BYTES_PER_FRAME]
            if len(chunk) == VAD_BYTES_PER_FRAME:
                is_speech = vad.is_speech(chunk, VAD_SAMPLE_RATE)
        if not is_speech:
            break
        count += 1
    return count


def vad_bargein_confirmed(frames: Sequence[bytes], confirm_frames: int) -> bool:
    """
    True if webrtcvad detects speech in at least 2 consecutive frames within the last confirm_frames window.
    Uses webrtcvad aggressiveness setting. Returns False if webrtcvad unavailable.
    ~60ms confirmation at 30ms frames when 2 consecutive are speech.
    """
    if not frames or confirm_frames < 1:
        return False
    try:
        vad = _get_vad()
    except RuntimeError:
        return False
    window_size = min(max(confirm_frames, 3), len(frames))
    tail = list(frames)[-window_size:]
    consecutive = 0
    for frame in reversed(tail):
        if len(frame) < VAD_BYTES_PER_FRAME:
            continue
        chunk = frame[:VAD_BYTES_PER_FRAME]
        if len(chunk) != VAD_BYTES_PER_FRAME:
            continue
        if vad.is_speech(chunk, VAD_SAMPLE_RATE):
            consecutive += 1
            if consecutive >= 2:
                return True
        else:
            consecutive = 0
    return False


def count_speech_frames_in_window(frames: Sequence[bytes]) -> int:
    """
    Return how many of the given frames are classified as speech by webrtcvad (each frame must be
    exactly VAD_BYTES_PER_FRAME bytes). Used for THREEPIO_DEBUG proof that VAD runs.
    """
    if not frames:
        return 0
    try:
        vad = _get_vad()
    except RuntimeError:
        return 0
    count = 0
    for frame in frames:
        chunk = frame[:VAD_BYTES_PER_FRAME]
        if len(chunk) != VAD_BYTES_PER_FRAME:
            continue
        if vad.is_speech(chunk, VAD_SAMPLE_RATE):
            count += 1
    return count


def count_speech_frames_combined(frames: Sequence[bytes], rms_list: Sequence[float]) -> int:
    """Count frames where webrtcvad says speech OR RMS >= THREEPIO_ENERGY_START (for debug window)."""
    if not frames or len(rms_list) < len(frames):
        return count_speech_frames_in_window(frames)
    try:
        vad = _get_vad()
    except RuntimeError:
        vad = None
    th = _energy_start_threshold()
    count = 0
    for i, frame in enumerate(frames):
        rms = rms_list[i] if i < len(rms_list) else 0.0
        if rms >= th:
            count += 1
            continue
        if vad is not None:
            chunk = frame[:VAD_BYTES_PER_FRAME]
            if len(chunk) == VAD_BYTES_PER_FRAME and vad.is_speech(chunk, VAD_SAMPLE_RATE):
                count += 1
    return count


def detect_speech_start(
    frames: Sequence[bytes],
    current_rms: float | None = None,
    current_peak: float | None = None,
    log_event: bool = True,
) -> bool:
    """True if the last few frames look like speech start (voice active)."""
    if not frames:
        return False
    try:
        vad = _get_vad()
    except RuntimeError:
        return False
    for frame in frames[-3:]:
        if len(frame) < VAD_BYTES_PER_FRAME:
            continue
        chunk = frame[:VAD_BYTES_PER_FRAME]
        if len(chunk) != VAD_BYTES_PER_FRAME:
            continue
        if vad.is_speech(chunk, VAD_SAMPLE_RATE):
            if log_event and _debug_enabled():
                rms_str = f" rms={current_rms:.4f}" if current_rms is not None else ""
                peak_str = f" peak={current_peak:.4f}" if current_peak is not None else ""
                print(f"[VAD] speech_start{rms_str}{peak_str}", flush=True)
                logger.debug("VAD speech_start%s%s", rms_str, peak_str)
            return True
    return False


def detect_speech_end(
    frames: Sequence[bytes],
    silence_ms_threshold: int = 700,
    current_rms: float | None = None,
    current_peak: float | None = None,
    log_event: bool = True,
) -> bool:
    """True if we have seen continuous silence for at least silence_ms_threshold."""
    if not frames:
        return False
    try:
        vad = _get_vad()
    except RuntimeError:
        return False
    required_silent_frames = max(1, silence_ms_threshold // VAD_FRAME_MS)
    silent_count = 0
    for frame in reversed(frames):
        if len(frame) < VAD_BYTES_PER_FRAME:
            continue
        chunk = frame[:VAD_BYTES_PER_FRAME]
        if len(chunk) != VAD_BYTES_PER_FRAME:
            continue
        if vad.is_speech(chunk, VAD_SAMPLE_RATE):
            return False
        silent_count += 1
        if silent_count >= required_silent_frames:
            if log_event and _debug_enabled():
                rms_str = f" rms={current_rms:.4f}" if current_rms is not None else ""
                peak_str = f" peak={current_peak:.4f}" if current_peak is not None else ""
                print(f"[VAD] speech_end{rms_str}{peak_str}", flush=True)
                logger.debug("VAD speech_end%s%s", rms_str, peak_str)
            return True
    return silent_count >= required_silent_frames


class VADMonitor:
    """
    Runs a thread that reads mic frames and invokes on_speech_start / on_speech_end.
    mode "listening": full VAD for speech start/end. mode "barge_in": speech_start only with
    confirmation and suppression window. Use set_speaking_start_ts(ts) when playback starts for barge_in.
    """

    def __init__(
        self,
        read_frame: Callable[[], bytes | None],
        on_speech_start: Callable[[], None],
        on_speech_end: Callable[[], None],
        *,
        silence_ms: int = 700,
        frame_bytes: int = VAD_BYTES_PER_FRAME,
        mode: Literal["listening", "barge_in"] = "listening",
        frame_queue: Queue[bytes] | None = None,
    ) -> None:
        self._read_frame = read_frame
        self._on_speech_start = on_speech_start
        self._on_speech_end = on_speech_end
        self._silence_ms = silence_ms
        self._frame_bytes = frame_bytes
        self._mode = mode
        self._frame_queue = frame_queue
        self._silence_frames = max(1, silence_ms // VAD_FRAME_MS)
        self._frames: deque[bytes] = deque(maxlen=100)
        self._rms_recent: deque[float] = deque(maxlen=50)
        self._in_speech = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_frame: bytes | None = None
        self._speaking_start_ts: float | None = None

    def set_speaking_start_ts(self, ts: float | None) -> None:
        """Set playback start time for barge_in suppression. None to clear."""
        self._speaking_start_ts = ts
        if ts is not None:
            self._in_speech = False

    def set_mode(self, mode: Literal["listening", "barge_in"]) -> None:
        """Switch between listening (full VAD) and barge_in (confirm + suppress)."""
        if mode != self._mode:
            self._mode = mode
            # Reset latch and buffers on mode switch
            self._in_speech = False
            self._frames.clear()
            self._rms_recent.clear()

    def get_last_frame(self) -> bytes | None:
        """Last frame read; used by ambient to seed listen_frames on barge-in."""
        return self._last_frame

    def start(self) -> None:
        """Spawn thread that reads frames and calls on_speech_start / on_speech_end."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to exit."""
        self._stop.set()

    def _run(self) -> None:
        from threepio.audio.mic_stream import frame_rms_peak

        while not self._stop.is_set():
            frame = self._read_frame()
            if frame is None:
                break
            self._last_frame = frame
            self._frames.append(frame)
            if self._frame_queue is not None:
                try:
                    self._frame_queue.put_nowait(frame)
                except Full:
                    # Drop oldest frame to keep real-time behavior
                    try:
                        _ = self._frame_queue.get_nowait()
                    except Empty:
                        pass
                    try:
                        self._frame_queue.put_nowait(frame)
                    except Full:
                        pass
            rms, peak = frame_rms_peak(frame)
            self._rms_recent.append(rms)
            list_frames = list(self._frames)
            rms_list = list(self._rms_recent)

            if self._mode == "barge_in":
                suppress_ms = get_speech_suppress_ms()
                elapsed_ms = (
                    (time.time() - self._speaking_start_ts) * 1000
                    if self._speaking_start_ts is not None
                    else suppress_ms + 1
                )
                suppression_remaining_ms = max(0, int(suppress_ms - elapsed_ms))
                if elapsed_ms < suppress_ms:
                    continue
                # Stricter barge-in: require sustained speech for N frames AND rms >= threshold * multiplier
                sustained_frames = get_bargein_sustained_frames()
                rms_mult = get_bargein_rms_multiplier()
                start_rms = get_vad_start_rms()
                rms_threshold = start_rms * rms_mult
                energy_th = get_energy_start_speaking()
                consecutive = _count_consecutive_speech_frames_from_tail(
                    list_frames, rms_list, energy_th
                )
                sustained_ok = consecutive >= sustained_frames
                rms_ok = rms >= rms_threshold
                speech_started = (
                    len(frame) >= self._frame_bytes and sustained_ok and rms_ok
                )
                if speech_started and not self._in_speech:
                    self._in_speech = True
                    if _debug_enabled():
                        print(
                            f"[ambient] barge-in accepted sustained_frames={consecutive} rms={rms:.4f} threshold={rms_threshold:.4f} suppression_remaining_ms={suppression_remaining_ms}",
                            flush=True,
                        )
                    try:
                        self._on_speech_start()
                    except Exception as e:
                        logger.debug("VADMonitor on_speech_start: %s", e)
                if not speech_started:
                    self._in_speech = False
                continue

            speech_started = (
                len(frame) >= self._frame_bytes
                and (
                    detect_speech_start(list_frames, current_rms=rms, current_peak=peak, log_event=False)
                    or energy_speech_start(rms_list, 3)
                )
            )
            speech_ended = (
                len(list_frames) >= self._silence_frames
                and (
                    detect_speech_end(
                        list_frames,
                        silence_ms_threshold=self._silence_ms,
                        current_rms=rms,
                        current_peak=peak,
                        log_event=False,
                    )
                    or energy_speech_end(rms_list, self._silence_frames)
                )
            )
            if speech_started and not self._in_speech:
                self._in_speech = True
                try:
                    self._on_speech_start()
                except Exception as e:
                    logger.debug("VADMonitor on_speech_start: %s", e)
            if speech_ended and self._in_speech:
                self._in_speech = False
                try:
                    self._on_speech_end()
                except Exception as e:
                    logger.debug("VADMonitor on_speech_end: %s", e)
