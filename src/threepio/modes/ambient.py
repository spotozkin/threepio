"""Ambient mode: continuous listen, TTS response, barge-in (stop playback when user speaks)."""

from __future__ import annotations

import logging
import os
import queue
import select
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from threepio.audio.mic_stream import (
    MicStream,
    frame_rms_peak,
    write_wav as write_wav_frames,
)
from threepio.audio.vad import (
    VAD_BYTES_PER_FRAME,
    VAD_FRAME_MS,
    VAD_SAMPLE_RATE,
    VADMonitor,
    count_speech_frames_combined,
    detect_speech_end,
    detect_speech_start,
    energy_bargein_confirmed,
    energy_speech_end,
    energy_speech_start,
    get_barge_in_baseline_floor,
    get_bargein_confirm_ms,
    get_energy_end_threshold,
    get_post_speech_cooldown_ms,
    get_speech_suppress_ms,
    get_vad_cooldown_ms,
    get_vad_start_rms,
    is_speaking_suppression_active,
    should_accept_speech,
    vad_speech_start_allowed,
)
from threepio.speech.playback import NO_PLAYER_MESSAGE, PlaybackHandle, play_audio_file_interruptible

logger = logging.getLogger(__name__)

CORR_SAMPLE_RATE = 16000


def _decode_audio_to_pcm_16k(path: Path) -> Any:
    """Decode WAV/MP3 to float32 mono 16kHz. Returns np.ndarray or empty array on failure."""
    import numpy as np

    path = Path(path)
    if not path.exists():
        return np.array([], dtype=np.float32)
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(path),
                "-f", "f32le", "-ar", str(CORR_SAMPLE_RATE), "-ac", "1",
                "-",
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return np.array([], dtype=np.float32)
        return np.frombuffer(proc.stdout, dtype=np.float32)
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return np.array([], dtype=np.float32)


def _frame_min_max_int16(frame: bytes) -> tuple[int, int]:
    """Min and max int16 value in frame (from first 960 bytes)."""
    n = min(len(frame) // 2, VAD_BYTES_PER_FRAME // 2)
    if n < 1:
        return (0, 0)
    try:
        samples = struct.unpack(f"<{n}h", frame[: n * 2])
        return (min(samples), max(samples))
    except struct.error:
        return (0, 0)


SILENCE_MS_THRESHOLD = 700
# After playback ends: discard captured audio for this long so we do not transcribe TTS echo (ms)
POST_PLAYBACK_DRAIN_MS = 400
# After barge-in: flush mic and ignore VAD for this long, then require fresh speech_start (ms)
POST_PLAYBACK_IGNORE_MS = 350


def _debug_enabled() -> bool:
    v = os.environ.get("THREEPIO_DEBUG", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _status(msg: str) -> None:
    print(f"[ambient] {msg}", flush=True)


def _load_user_profile_fns() -> tuple[Any, ...]:
    """
    Load user_profile helpers or return no-op fallbacks if the module is missing.
    Returns (get_preferred_address, load_profile, mark_addressed, save_profile, should_inject_address, update_from_user_text).
    """
    try:
        from threepio.memory.user_profile import (
            get_preferred_address,
            load_or_prompt_profile,
            load_profile,
            mark_addressed,
            save_profile,
            should_inject_address,
            update_from_user_text,
        )
        return (
            get_preferred_address,
            load_or_prompt_profile,
            load_profile,
            mark_addressed,
            save_profile,
            should_inject_address,
            update_from_user_text,
        )
    except ModuleNotFoundError as e:
        if "user_profile" in str(e):
            _status("memory disabled: threepio.memory.user_profile not found")
            logger.info("user_profile not found, using no-op fallbacks: %s", e)
        else:
            raise
        def _default_profile() -> Any:
            return SimpleNamespace(
                last_addressed_at=None, times_seen=0, name=None, preferred_address=None,
                display_name=None, address_style="neutral", custom_address=None, pronouns=None, speaker_id="default",
            )
        return (
            lambda p: None,
            lambda base_dir=".": _default_profile(),
            lambda speaker_id="default", base_dir=".": _default_profile(),
            lambda p, now: None,
            lambda p, base_dir=".": None,
            lambda p, now, cooldown_s=90.0: False,
            lambda profile, text: profile if profile is not None else {},
        )


def _load_classify_fn() -> Any:
    """
    Load persona governor classify or return a fallback if c3po_governor is missing.
    Fallback returns {"allow": True} so the pipeline continues with normal assistant replies.
    """
    try:
        from threepio.persona.c3po_governor import classify
        return classify
    except (ModuleNotFoundError, ImportError) as e:
        if "c3po_governor" in str(e):
            _status("persona governor disabled: threepio.persona.c3po_governor not found")
            logger.info("c3po_governor not found, using allow-all fallback: %s", e)
        else:
            raise

        def _classify_fallback(text: str) -> dict[str, Any]:
            return {"allow": True}

        return _classify_fallback


def _load_address_gating_fns() -> Any:
    """
    Load extract_speaker_address from address_gating or return a no-op fallback if the module is missing.
    Fallback returns None so the pipeline continues without speaker address extraction.
    """
    try:
        from threepio.persona.address_gating import extract_speaker_address
        return extract_speaker_address
    except ModuleNotFoundError as e:
        if "address_gating" in str(e):
            _status("address gating disabled: threepio.persona.address_gating not found")
            logger.info("address_gating not found, using no-op fallback: %s", e)
        else:
            raise

        def _extract_speaker_address_fallback(profile: Any, *args: Any, **kwargs: Any) -> None:
            return None

        return _extract_speaker_address_fallback


def _load_flavor_governor_fn() -> Any:
    """
    Load flavor_intent from flavor_governor or return a no-op fallback if the module is missing.
    Fallback returns None (no special flavor / default) so the pipeline continues.
    """
    try:
        from threepio.persona.flavor_governor import flavor_intent
        return flavor_intent
    except ModuleNotFoundError as e:
        if "flavor_governor" in str(e):
            _status("flavor governor disabled: threepio.persona.flavor_governor not found")
            logger.info("flavor_governor not found, using fallback: %s", e)
        else:
            raise

        def _flavor_intent_fallback(text: str, *args: Any, **kwargs: Any) -> None:
            return None

        return _flavor_intent_fallback


def _load_prompt_builder_fn() -> Any:
    """Load build_c3po_system_prompt or return fallback that gives a default prompt."""
    try:
        from threepio.persona.prompt_builder import build_c3po_system_prompt
        return build_c3po_system_prompt
    except (ModuleNotFoundError, ImportError) as e:
        if "prompt_builder" in str(e) or "persona" in str(e):
            _status("prompt_builder disabled: using default THREEPIO prompt")
            logger.info("prompt_builder not found: %s", e)
        else:
            raise

        def _prompt_fallback(profile: Any = None, *, mode: str = "ambient") -> str:
            return "You are THREEPIO, a helpful C-3PO-inspired assistant."

        return _prompt_fallback


def _load_slang_gloss_fn() -> Any:
    """Load slang_to_formal_gloss or return no-op (identity)."""
    try:
        from threepio.persona.reality_threepio import slang_to_formal_gloss
        return slang_to_formal_gloss
    except (ModuleNotFoundError, ImportError):
        return lambda text: ""


def _load_notes_fns() -> tuple[Any, Any, Any]:
    """Load add_note, extract_note_from_user_text, should_save_note or no-ops."""
    try:
        from threepio.memory.notes import add_note, extract_note_from_user_text, should_save_note
        return add_note, extract_note_from_user_text, should_save_note
    except (ModuleNotFoundError, ImportError):
        return (
            lambda title, content: None,
            lambda text: (None, None),
            lambda text: False,
        )


def _load_semantic_filter_fn() -> Any:
    """Load interpret_user_intent for slang-to-formal interpretation, or no-op."""
    try:
        from threepio.persona.semantic_filter import interpret_user_intent
        return interpret_user_intent
    except (ModuleNotFoundError, ImportError):
        return lambda text: ""


def transcribe_wav(path: Path, settings: Any) -> tuple[str, Any]:
    """
    Transcribe WAV file to text. Uses local faster-whisper with STT_* settings.
    Returns (text, info) where info has .language (detected or requested).
    Raises RuntimeError with instructions if STT is not available.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"WAV not found: {path}")
    model_size = getattr(settings, "STT_MODEL", "tiny")
    language = getattr(settings, "STT_LANGUAGE", "en")
    if language == "":
        language = None
    beam_size = getattr(settings, "STT_BEAM_SIZE", 1)
    try:
        from threepio.speech.stt.local_whisper import transcribe as local_whisper_transcribe
        stt_t0 = time.perf_counter()
        text, info = local_whisper_transcribe(path, model_size=model_size, language=language, beam_size=beam_size)
        print(f"[perf] stt_sec={time.perf_counter() - stt_t0:.3f}", flush=True)
        detected = getattr(info, "language", None)
        logger.debug(
            "[ambient] stt model=%s language=%s transcript=%s",
            model_size,
            detected or language,
            (text or "")[:80],
        )
        return (text.strip(), info)
    except ImportError as e:
        raise RuntimeError(
            "STT required for --ambient. Install faster-whisper:\n"
            "  pip install faster-whisper\n"
            "Then run again. The ambient loop is ready; only transcription was missing."
        ) from e
    except Exception as e:
        if "faster-whisper" in str(e).lower() or "faster_whisper" in str(e):
            raise RuntimeError(
                "STT required for --ambient. Install faster-whisper:\n"
                "  pip install faster-whisper\n"
                "Then run again."
            ) from e
        raise


def run_vad_test(device_in: int | None = None, duration_sec: float = 10.0) -> None:
    """
    Run mic capture for duration_sec and print rms/peak plus whether speech would be accepted
    (RMS gate only; no STT/LLM/TTS). Use to tune THREEPIO_VAD_START_RMS and related env vars.
    """
    from threepio.audio.devices import resolve_input_device

    if device_in is None:
        selector = os.environ.get("THREEPIO_AUDIO_INPUT_DEVICE", "").strip() or None
    else:
        selector = str(device_in)
    try:
        idx, name = resolve_input_device(selector)
    except RuntimeError as e:
        _status(str(e))
        return
    mic = MicStream(device=idx)
    try:
        mic.start()
    except Exception as e:
        _status(f"Mic failed: {e}")
        return
    _status(f"VAD test: {duration_sec}s capture on device {idx}. Speak to see rms/would_accept.")
    start = time.time()
    preroll: list[bytes] = []
    recent_frames: list[bytes] = []
    rms_recent: deque[float] = deque(maxlen=50)
    frame_queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
    log_interval = 0.3
    last_log_ts = 0.0
    start_rms = get_vad_start_rms()
    cooldown_ms = get_vad_cooldown_ms()
    try:
        while time.time() - start < duration_sec:
            try:
                frame = mic.read_frame()
            except Exception:
                break
            if frame is None or len(frame) != VAD_BYTES_PER_FRAME:
                continue
            rms, peak = frame_rms_peak(frame)
            rms_recent.append(rms)
            recent_frames.append(frame)
            if len(recent_frames) > 30:
                recent_frames.pop(0)
            vad_start = detect_speech_start(
                preroll + recent_frames, current_rms=rms, current_peak=peak, log_event=False
            )
            energy_start = energy_speech_start(rms_recent, n_frames=3)
            is_vad_speech = vad_start or energy_start
            now_ms = int(time.time() * 1000)
            would_accept = should_accept_speech(is_vad_speech, rms, now_ms, 0, start_rms, cooldown_ms)
            now = time.time()
            if now - last_log_ts >= log_interval:
                last_log_ts = now
                print(
                    f"[vad-test] rms={rms:.4f} peak={peak:.4f} vad={vad_start} energy={energy_start} "
                    f"would_accept={would_accept} (threshold={start_rms})",
                    flush=True,
                )
    finally:
        mic.stop()
    _status("VAD test done.")


def run(
    settings: Any,
    device_in: int | None = None,
    vad_threshold: float | None = None,
) -> int:
    """
    Single public entrypoint for ambient mode. Starts the state machine loop and blocks.
    Returns 0 if loop exits normally (SIGTERM/SIGINT), 1 if startup failed or exited early.
    """
    _status("starting")
    # Startup diagnostics: list input devices and output mode
    try:
        from threepio.audio.devices import format_input_devices, list_input_devices
        devs = list_input_devices()
        if devs:
            logger.info("Audio input devices: %s", format_input_devices(devs).replace("\n", " | "))
            print("[ambient] input devices: " + format_input_devices(devs).replace("\n", " | "), flush=True)
        else:
            print("[ambient] input devices: none found", flush=True)
    except Exception as e:
        logger.debug("Could not list input devices: %s", e)
    out_mode = getattr(settings, "AUDIO_OUTPUT_MODE", "auto") or "auto"
    out_dev = os.environ.get("THREEPIO_AUDIO_OUTPUT_DEVICE", "").strip() or getattr(settings, "AUDIO_OUTPUT_DEVICE", None)
    out_dev_str = str(out_dev) if out_dev else "(default)"
    logger.info("AUDIO_OUTPUT_MODE=%s THREEPIO_AUDIO_OUTPUT_DEVICE=%s", out_mode, out_dev_str)
    print(f"[ambient] output mode={out_mode} device={out_dev_str}", flush=True)

    mode = out_mode
    try:
        from threepio.speech.playback import get_playback_command_with_mode
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            probe_path = Path(f.name)
        try:
            probe_path.write_bytes(b"\x00" * 960)
            _, playback_name = get_playback_command_with_mode(probe_path, mode)
        finally:
            probe_path.unlink(missing_ok=True)
    except Exception:
        playback_name = mode
    _status(f"playback={playback_name}")
    barge_in_mode = getattr(settings, "BARGE_IN_MODE", "full") or "full"
    logger.info("BARGE_IN_MODE=%s", barge_in_mode)
    print(f"[ambient] startup BARGE_IN_MODE={barge_in_mode}", flush=True)

    silence_ms = int(vad_threshold) if vad_threshold is not None else SILENCE_MS_THRESHOLD
    return run_ambient(mic_device=device_in, silence_ms=silence_ms)


def run_ambient(
    *,
    mic_device: int | str | None = None,
    silence_ms: int = SILENCE_MS_THRESHOLD,
) -> int:
    """
    Run ambient loop: IDLE -> LISTENING -> THINKING -> SPEAKING.
    Barge-in: when user speaks during SPEAKING, stop playback and go to LISTENING.
    Returns 0 on graceful shutdown (SIGTERM/SIGINT), 1 on startup failure or early exit.
    """
    from threepio.config.settings import get_settings
    from threepio.llm.provider import generate_reply, get_llm_client
    get_preferred_address, load_or_prompt_profile, load_profile, mark_addressed, save_profile, should_inject_address, update_from_user_text = _load_user_profile_fns()
    # Classify from loader only (no direct c3po_governor import) so ambient runs if that module is missing
    classify = _load_classify_fn()
    extract_speaker_address = _load_address_gating_fns()
    flavor_intent = _load_flavor_governor_fn()
    build_c3po_system_prompt = _load_prompt_builder_fn()
    slang_to_formal_gloss = _load_slang_gloss_fn()
    interpret_user_intent = _load_semantic_filter_fn()
    add_note, extract_note_from_user_text, should_save_note = _load_notes_fns()
    from threepio.speech.echo_guard import apply_echo_guard
    from threepio.speech.text_shaping import shape_for_speech
    from threepio.speech.tts.provider import get_tts_provider, synthesize_to_file

    # State
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    state = IDLE

    settings = get_settings()
    tts = get_tts_provider()
    try:
        llm_client = get_llm_client()
    except Exception as e:
        _status(f"LLM unavailable: {e}. --ambient requires OPENAI_API_KEY and PROVIDER_LLM=openai.")
        return 1

    base_dir = Path(".").resolve()
    # First-run profile from .threepio/profile.json (prompt if missing and interactive)
    profile = load_or_prompt_profile(base_dir)
    # Merge runtime state from data/memory/profiles.json if present
    existing = load_profile("default", base_dir)
    if getattr(existing, "last_addressed_at", None) is not None:
        profile.last_addressed_at = existing.last_addressed_at
    if getattr(existing, "times_seen", 0):
        profile.times_seen = existing.times_seen
    if getattr(existing, "name", None) and not profile.name:
        profile.name = existing.name
    if getattr(existing, "preferred_address", None) and not profile.preferred_address:
        profile.preferred_address = existing.preferred_address
    messages: list[dict[str, str]] = []
    speaker_address: str | None = None
    system_prompt = None  # built per turn

    # Resolve input device: numeric string → int index; else substring match (input-capable only)
    from threepio.audio.devices import resolve_input_device

    if mic_device is None:
        selector = os.environ.get("THREEPIO_AUDIO_INPUT_DEVICE", "").strip() or None
        if not selector and getattr(settings, "AUDIO_INPUT_DEVICE", None) is not None:
            selector = str(settings.AUDIO_INPUT_DEVICE)
    else:
        selector = str(mic_device)
    try:
        idx, name = resolve_input_device(selector)
    except RuntimeError as e:
        _status(str(e))
        return 1
    _status(f"resolved input: index={idx} name='{name}' (THREEPIO_AUDIO_INPUT_DEVICE or default)")
    mic = MicStream(device=idx)
    try:
        mic.start()
    except Exception as e:
        _status(f"Mic failed: {e}")
        return 1

    _status("Listening. Speak to start; speak again during reply to barge-in.")
    # Min utterance: THREEPIO_MIN_UTTERANCE_SEC overrides settings.MIN_UTTERANCE_SEC
    _min_utterance_env = os.environ.get("THREEPIO_MIN_UTTERANCE_SEC", "").strip()
    min_utterance_sec = float(_min_utterance_env) if _min_utterance_env else getattr(settings, "MIN_UTTERANCE_SEC", 1.2)
    if _debug_enabled():
        print(f"[ambient] min_utterance_sec={min_utterance_sec}", flush=True)
        print("[ambient] state=IDLE", flush=True)

    listen_frames: list[bytes] = []
    max_listen_frames = 300  # ~9s cap
    debug_frame_count = 0
    silent_seconds = 0.0
    last_level_time = None
    silent_warning_printed = False
    vad_debug_window: deque[bytes] = deque(maxlen=30)
    vad_debug_rms: deque[float] = deque(maxlen=30)
    last_vad_debug_log_time: float | None = None
    silence_frames = max(1, silence_ms // VAD_FRAME_MS)
    rms_recent: deque[float] = deque(maxlen=max(silence_frames + 5, 50))
    cooldown_until_ts: float | None = None
    last_cooldown_log_at: float | None = None  # throttle "trigger ignored (post-speech cooldown)" to once per second
    reject_cooldown_until_ts: float | None = None  # after "too short" or "no speech detected"
    last_reject_ts: float | None = None  # timestamp when we last rejected (for should_accept_speech)
    bargein_debounce_frames = 0  # after barge-in, discard this many frames before accumulating listen_frames
    post_playback_drain_until_ts: float | None = None  # after SPEAKING ends, discard frames until this time (no STT of TTS echo)
    post_playback_ignore_until_ts: float | None = None  # after barge-in: flush mic + ignore VAD until this time, then require fresh speech_start
    utterance_ms_acc = 0  # accumulated ms in current utterance (reset on speech_start and after finalize)
    silence_ms_acc = 0  # consecutive silence ms (reset when vad_is_speech; used for silence-hangover end)

    frame_queue: queue.Queue[bytes] = queue.Queue(maxsize=50)
    from threepio.audio.ring_buffer import RingBuffer
    from threepio.audio.correlation import compute_best_abs_corr

    mic_ring = RingBuffer(capacity_ms=1200, sample_rate=CORR_SAMPLE_RATE)
    speaker_pcm_ref: list[Any] = [None]
    playback_start_ts_ref: list[float | None] = [None]
    baseline_freeze_rms_ref: list[float | None] = [None]  # frozen at playback start; used for eff_min_rms during playback
    corr_echo_samples_ref: list[list[float]] = [[]]  # collect corr values during first 1500ms when echo-only (mic not spiking)
    corr_echo_ref: list[float | None] = [None]  # median of echo corr; adaptive allow cutoff = min(ALLOW_THRESH, corr_echo_ref*0.60)
    CORR_ECHO_COLLECT_MS = 1500
    speaker_lock = threading.Lock()
    raw_path: Path | None = None
    playback_path: Path | None = None
    state_ref: list[str] = [state]
    handle_ref: list[PlaybackHandle | None] = [None]
    shutdown_requested_ref: list[bool] = [False]
    graceful_exit_ref: list[bool] = [False]  # True when exiting due to SIGTERM/SIGINT
    ffmpeg_checked_ref: list[bool] = [False]
    ffmpeg_available_ref: list[bool] = [True]

    def _on_bargein_speech_start(speech_ms: int = 0, max_rms: float = 0.0, suppression_active: bool = False) -> None:
        if state_ref[0] != SPEAKING:
            return
        # THREEPIO_ENABLE_BARGE_IN (default true). When false, never interrupt playback.
        enable = os.environ.get("THREEPIO_ENABLE_BARGE_IN", os.environ.get("THREEPIO_BARGE_IN", "1")).strip().lower()
        if enable in ("0", "false", "no"):
            if _debug_enabled():
                print("[ambient] barge-in disabled (THREEPIO_ENABLE_BARGE_IN=false)", flush=True)
            return
        barge_in_mode = (os.environ.get("BARGE_IN_MODE") or getattr(settings, "BARGE_IN_MODE", "full") or "full").strip().lower()
        if barge_in_mode in ("off", "assisted"):
            return
        def _barge_env_int(name: str, default: int) -> int:
            v = os.environ.get(name, os.environ.get("THREEPIO_" + name, "")).strip()
            if not v:
                return getattr(settings, name, default) if hasattr(settings, name) else default
            try:
                return max(0, int(v))
            except ValueError:
                return default

        def _barge_env_float(name: str, default: float) -> float:
            v = os.environ.get(name, os.environ.get("THREEPIO_" + name, "")).strip()
            if not v:
                return getattr(settings, name, default) if hasattr(settings, name) else default
            try:
                return max(0.0, float(v))
            except ValueError:
                return default

        min_speech_ms = _barge_env_int("BARGE_IN_MIN_SPEECH_MS", 250)
        min_rms = _barge_env_float("BARGE_IN_MIN_RMS", 0.0)
        baseline_floor = _barge_env_float("BARGE_IN_BASELINE_FLOOR", 0.006)
        echo_floor = _barge_env_float("BARGE_IN_PLAYBACK_ECHO_FLOOR", 0.070)
        suppression_barge_mult = _barge_env_float("BARGE_IN_SUPPRESSION_BARGE_MULT", 1.35)
        margin_mult_playback = _barge_env_float("BARGE_IN_MARGIN_MULT_PLAYBACK", 1.6)
        margin_add_playback = _barge_env_float("BARGE_IN_MARGIN_ADD_PLAYBACK", 0.010)
        corr_window_ms = _barge_env_int("BARGE_IN_CORR_WINDOW_MS", 200)
        corr_lag_sweep_ms = _barge_env_int("BARGE_IN_CORR_LAG_SWEEP_MS", 60)
        corr_lag_step_ms = _barge_env_int("BARGE_IN_CORR_LAG_STEP_MS", 10)
        corr_block_thresh = _barge_env_float("BARGE_IN_CORR_BLOCK_THRESH", 0.65)
        corr_allow_thresh = _barge_env_float("BARGE_IN_CORR_ALLOW_THRESH", 0.45)
        corr_uncertain_rms_mult = _barge_env_float("BARGE_IN_CORR_UNCERTAIN_RMS_MULT", 1.25)
        corr_confident_min = _barge_env_float("BARGE_IN_CORR_CONFIDENT_MIN", 0.15)
        baseline_idle_rms = baseline_freeze_rms_ref[0] if baseline_freeze_rms_ref[0] is not None else vad_monitor.get_baseline_rms()
        if baseline_idle_rms is not None:
            baseline_idle_rms = max(baseline_idle_rms, baseline_floor)
        if baseline_freeze_rms_ref[0] is not None:
            print(f"[barge-in] baseline_freeze active={baseline_freeze_rms_ref[0]:.4f}", flush=True)
        if baseline_idle_rms is not None and baseline_idle_rms > 0:
            effective_min_rms = (
                baseline_idle_rms * margin_mult_playback + margin_add_playback
            )
            effective_min_rms = max(effective_min_rms, min_rms)
        else:
            effective_min_rms = max(min_rms, baseline_floor)
        idle_baseline_str = f"{baseline_idle_rms:.4f}" if baseline_idle_rms is not None else "None"

        corr_val: float | None = None
        lag_ms_val: int | None = None
        corr_na_reason: str | None = None
        decision = "NO_TRIGGER"
        N_samp = int(CORR_SAMPLE_RATE * corr_window_ms / 1000)
        sweep_samp = int(CORR_SAMPLE_RATE * corr_lag_sweep_ms / 1000)
        required_spk = N_samp + 2 * sweep_samp
        warmup_ms = _barge_env_int("BARGE_IN_PLAYBACK_WARMUP_MS", 350)
        mic_seg = mic_ring.read_last_samples(N_samp)
        spk_seg = None
        elapsed_ms = 0.0
        spk_len = 0
        with speaker_lock:
            pcm = speaker_pcm_ref[0]
            start_ts = playback_start_ts_ref[0]
        if pcm is not None and start_ts is not None:
            elapsed_ms = (time.time() - start_ts) * 1000
            end_samp = min(len(pcm), int(elapsed_ms * CORR_SAMPLE_RATE / 1000))
            start_samp = max(0, end_samp - required_spk)
            spk_len = end_samp - start_samp
            if spk_len >= required_spk:
                spk_seg = pcm[start_samp:end_samp]
        mic_len = int(getattr(mic_seg, "size", len(mic_seg)))
        if spk_seg is not None:
            spk_len = int(getattr(spk_seg, "size", len(spk_seg)))
        print(
            f"[barge-in] corr_debug mic_sr={CORR_SAMPLE_RATE} spk_sr={CORR_SAMPLE_RATE} N={N_samp} sweep={sweep_samp} mic_len={mic_len} spk_len={spk_len} required_spk={required_spk}",
            flush=True,
        )
        if elapsed_ms < warmup_ms:
            decision = "NO_TRIGGER"
            print(f"[barge-in] warmup_block elapsed_ms={elapsed_ms:.0f}", flush=True)
            return
        if spk_len < required_spk or mic_len < N_samp:
            corr_na_reason = "insufficient_samples"
            print(
                f"[barge-in] corr_na reason=insufficient_samples mic_len={mic_len} spk_len={spk_len} N={N_samp} sweep={sweep_samp}",
                flush=True,
            )
        elif mic_seg.size >= N_samp and spk_seg is not None and spk_seg.size >= required_spk:
            corr_val, lag_ms_val, corr_na_reason = compute_best_abs_corr(
                mic_seg, spk_seg, CORR_SAMPLE_RATE, corr_lag_sweep_ms, corr_lag_step_ms
            )
            if corr_val is None and corr_na_reason is not None:
                print(
                    f"[barge-in] corr_na reason={corr_na_reason} mic_len={mic_len} spk_len={spk_len} N={N_samp} sweep={sweep_samp}",
                    flush=True,
                )
        if corr_val is not None and corr_val < corr_confident_min:
            corr_val = None
            lag_ms_val = None

        nearfield_min = max(echo_floor * 1.6, effective_min_rms * 2.0)
        if corr_val is not None and lag_ms_val is not None and spk_seg is not None:
            import numpy as np
            mic_rms_w = float(np.sqrt(np.mean(np.asarray(mic_seg, dtype=np.float64) ** 2)))
            lag_samp = int(lag_ms_val * CORR_SAMPLE_RATE / 1000)
            idx = sweep_samp + lag_samp
            idx = max(0, min(idx, spk_seg.size - N_samp))
            spk_slice = spk_seg[idx : idx + N_samp]
            spk_rms_w = float(np.sqrt(np.mean(np.asarray(spk_slice, dtype=np.float64) ** 2)))
            print(
                f"[barge-in] corr_val corr={corr_val:.4f} lag_ms={lag_ms_val} mic_rms={mic_rms_w:.4f} spk_rms={spk_rms_w:.4f}",
                flush=True,
            )

        if corr_val is not None and elapsed_ms >= warmup_ms and elapsed_ms < CORR_ECHO_COLLECT_MS and max_rms < nearfield_min:
            corr_echo_samples_ref[0].append(corr_val)
        if elapsed_ms >= CORR_ECHO_COLLECT_MS and corr_echo_ref[0] is None and corr_echo_samples_ref[0]:
            s = sorted(corr_echo_samples_ref[0])
            n = len(s)
            corr_echo_ref[0] = (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2.0)

        if corr_val is not None:
            if corr_val >= corr_block_thresh:
                decision = "BLOCK_CORR"
                print(
                    f"[barge-in] playback=True suppression={suppression_active} flush=False speech_ms={speech_ms} mic_rms={max_rms:.4f} idle_baseline={idle_baseline_str} eff_min_rms={effective_min_rms:.4f} corr={corr_val:.4f} lag_ms={lag_ms_val} echo_floor={echo_floor:.4f} decision={decision}",
                    flush=True,
                )
                return
            if corr_val <= (allow_cutoff := (min(corr_allow_thresh, corr_echo_ref[0] * 0.60) if corr_echo_ref[0] is not None else corr_allow_thresh)):
                allow_min_rms = max(effective_min_rms, echo_floor * 1.05)
                if speech_ms < min_speech_ms or max_rms < allow_min_rms:
                    decision = "NO_TRIGGER"
                    _ce = corr_echo_ref[0]
                    _ce_str = f"{_ce:.4f}" if _ce is not None else "None"
                    print(
                        f"[barge-in] corr_echo_ref={_ce_str} corr={corr_val:.4f} allow_cutoff={allow_cutoff:.4f} playback=True suppression={suppression_active} flush=False speech_ms={speech_ms} mic_rms={max_rms:.4f} idle_baseline={idle_baseline_str} eff_min_rms={effective_min_rms:.4f} lag_ms={lag_ms_val} echo_floor={echo_floor:.4f} decision={decision}",
                        flush=True,
                    )
                    return
                decision = "ALLOW_CORR"
                _ce = corr_echo_ref[0]
                _ce_str = f"{_ce:.4f}" if _ce is not None else "None"
                print(
                    f"[barge-in] corr_echo_ref={_ce_str} corr={corr_val:.4f} allow_cutoff={allow_cutoff:.4f}",
                    flush=True,
                )
            else:
                decision = "UNCERTAIN_NO_TRIGGER"
                print(
                    f"[barge-in] playback=True suppression={suppression_active} flush=False speech_ms={speech_ms} mic_rms={max_rms:.4f} idle_baseline={idle_baseline_str} eff_min_rms={effective_min_rms:.4f} corr={corr_val:.4f} lag_ms={lag_ms_val} echo_floor={echo_floor:.4f} decision={decision}",
                    flush=True,
                )
                return
        else:
            _bf = baseline_freeze_rms_ref[0] or 0.0
            nearfield_threshold = max(
                echo_floor * 2.5,
                effective_min_rms * 3.0,
                _bf * 8.0,
            )
            print(
                f"[barge-in] nearfield_threshold={nearfield_threshold:.4f} mic_rms={max_rms:.4f}",
                flush=True,
            )
            if speech_ms < min_speech_ms or max_rms < nearfield_threshold:
                decision = "NO_TRIGGER"
                print(
                    f"[barge-in] playback=True suppression={suppression_active} flush=False speech_ms={speech_ms} mic_rms={max_rms:.4f} idle_baseline={idle_baseline_str} eff_min_rms={effective_min_rms:.4f} corr=NA lag_ms=NA echo_floor={echo_floor:.4f} decision={decision}",
                    flush=True,
                )
                return
            decision = "FALLBACK_NEARFIELD"
            print(
                f"[barge-in] playback=True suppression={suppression_active} flush=False speech_ms={speech_ms} mic_rms={max_rms:.4f} idle_baseline={idle_baseline_str} eff_min_rms={effective_min_rms:.4f} corr=NA lag_ms=NA echo_floor={echo_floor:.4f} decision={decision}",
                flush=True,
            )
        if suppression_active and max_rms <= (echo_floor * suppression_barge_mult):
            decision = "NO_TRIGGER"
            corr_str = f"{corr_val:.4f}" if corr_val is not None else "NA"
            lag_str = str(lag_ms_val) if lag_ms_val is not None else "NA"
            print(
                f"[barge-in] playback=True suppression={suppression_active} flush=False speech_ms={speech_ms} mic_rms={max_rms:.4f} idle_baseline={idle_baseline_str} eff_min_rms={effective_min_rms:.4f} corr={corr_str} lag_ms={lag_str} echo_floor={echo_floor:.4f} decision={decision}",
                flush=True,
            )
            return
        corr_str = f"{corr_val:.4f}" if corr_val is not None else "NA"
        lag_str = str(lag_ms_val) if lag_ms_val is not None else "NA"
        print(
            f"[barge-in] playback=True suppression={suppression_active} flush=False speech_ms={speech_ms} mic_rms={max_rms:.4f} idle_baseline={idle_baseline_str} eff_min_rms={effective_min_rms:.4f} corr={corr_str} lag_ms={lag_str} echo_floor={echo_floor:.4f} decision={decision}",
            flush=True,
        )
        # Passed gate; continue to stop playback
        h = handle_ref[0]
        if h is not None and h.is_running():
            h.stop()
        handle_ref[0] = None
        with speaker_lock:
            speaker_pcm_ref[0] = None
            playback_start_ts_ref[0] = None
        baseline_freeze_rms_ref[0] = None
        corr_echo_samples_ref[0] = []
        corr_echo_ref[0] = None
        # Do NOT start capture yet: flush mic and require fresh speech_start to avoid transcribing TTS leakage
        state_ref[0] = IDLE
        listen_frames.clear()
        ignore_ms = int(os.environ.get("THREEPIO_POST_PLAYBACK_IGNORE_MS", str(POST_PLAYBACK_IGNORE_MS)))
        nonlocal bargein_debounce_frames, post_playback_ignore_until_ts
        bargein_debounce_frames = int(
            os.environ.get("THREEPIO_BARGEIN_DEBOUNCE_FRAMES", "2")
        )
        post_playback_ignore_until_ts = time.time() + (ignore_ms / 1000.0)
        vad_monitor.set_baseline_freeze_until_ts(post_playback_ignore_until_ts)
        vad_monitor.set_mode("listening")
        print("[barge-in] accepted, stopping playback (via=VADMonitor)", flush=True)
        print(f"[barge-in] stopped playback, flushing mic for {ignore_ms}ms", flush=True)
        _status("Barge-in. Flushing mic...")
        if _debug_enabled():
            print("[ambient] barge-in -> LISTENING", flush=True)

    def _on_speech_end_listening() -> None:
        # Main loop drives LISTENING->THINKING via detect_speech_end; no-op here to avoid duplicate
        pass

    vad_monitor = VADMonitor(
        read_frame=mic.read_frame,
        on_speech_start=_on_bargein_speech_start,
        on_speech_end=_on_speech_end_listening,
        silence_ms=silence_ms,
        frame_bytes=VAD_BYTES_PER_FRAME,
        mode="listening",
        frame_queue=frame_queue,
        mic_ring_buffer=mic_ring,
    )
    vad_monitor.start()

    def _shutdown_handler(signum: int, _frame: Any) -> None:
        sig_name = "SIGTERM" if signum == signal.SIGTERM else "SIGINT" if signum == signal.SIGINT else str(signum)
        print(f"[ambient] shutdown requested ({sig_name})", flush=True)
        shutdown_requested_ref[0] = True

    try:
        signal.signal(signal.SIGTERM, _shutdown_handler)
        signal.signal(signal.SIGINT, _shutdown_handler)
    except (ValueError, OSError):
        pass  # main thread only; ignore on some platforms

    try:
        while True:
            if shutdown_requested_ref[0]:
                graceful_exit_ref[0] = True
                break
            if state_ref[0] == SPEAKING:
                # Playback active: do NOT run utterance capture or STT (prevents self-transcription of TTS). VADMonitor barge-in runs only when BARGE_IN_MODE=full.
                state = SPEAKING
                tty_saved = None
                while (
                    handle_ref[0] is not None
                    and handle_ref[0].is_running()
                    and state_ref[0] == SPEAKING
                    and not shutdown_requested_ref[0]
                ):
                    barge_in_mode = (os.environ.get("BARGE_IN_MODE") or getattr(settings, "BARGE_IN_MODE", "full") or "full").strip().lower()
                    if barge_in_mode == "assisted":
                        try:
                            import termios
                            if tty_saved is None and sys.stdin.isatty():
                                tty_saved = termios.tcgetattr(sys.stdin)
                                new = list(tty_saved)
                                new[3] = new[3] & ~(termios.ICANON | termios.ECHO)
                                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new)
                            if tty_saved is not None:
                                r, _, _ = select.select([sys.stdin], [], [], 0)
                                if r:
                                    ch = sys.stdin.read(1)
                                    if ch in "\r\n ":
                                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, tty_saved)
                                        tty_saved = None
                                        print("[barge-in] assisted_interrupt_triggered source=keypress", flush=True)
                                        h = handle_ref[0]
                                        if h is not None and h.is_running():
                                            h.stop()
                                        handle_ref[0] = None
                                        state_ref[0] = IDLE
                                        with speaker_lock:
                                            speaker_pcm_ref[0] = None
                                            playback_start_ts_ref[0] = None
                                        baseline_freeze_rms_ref[0] = None
                                        corr_echo_samples_ref[0] = []
                                        corr_echo_ref[0] = None
                                        listen_frames.clear()
                                        ignore_ms = 350
                                        post_playback_ignore_until_ts = time.time() + (ignore_ms / 1000.0)
                                        vad_monitor.set_baseline_freeze_until_ts(post_playback_ignore_until_ts)
                                        vad_monitor.set_mode("listening")
                                        vad_monitor.set_speaking_start_ts(None)
                                        print(f"[barge-in] stopped playback, flushing mic for {ignore_ms}ms", flush=True)
                                        _status("Barge-in (assisted). Flushing mic...")
                                        break
                        except Exception:
                            if tty_saved is not None:
                                try:
                                    import termios
                                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, tty_saved)
                                except Exception:
                                    pass
                                tty_saved = None
                    time.sleep(0.02)
                if tty_saved is not None:
                    try:
                        import termios
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, tty_saved)
                    except Exception:
                        pass
                if state_ref[0] == SPEAKING:
                    state_ref[0] = IDLE
                    state = IDLE
                    vad_monitor.set_mode("listening")
                    vad_monitor.set_speaking_start_ts(None)
                    handle_ref[0] = None
                    with speaker_lock:
                        speaker_pcm_ref[0] = None
                        playback_start_ts_ref[0] = None
                    baseline_freeze_rms_ref[0] = None
                    corr_echo_samples_ref[0] = []
                    corr_echo_ref[0] = None
                    _status("Idle.")
                    cooldown_until_ts = time.time() + (get_post_speech_cooldown_ms() / 1000.0)
                    post_playback_drain_until_ts = time.time() + (POST_PLAYBACK_DRAIN_MS / 1000.0)
                    vad_monitor.set_baseline_freeze_until_ts(post_playback_drain_until_ts)
                if raw_path is not None and raw_path.exists():
                    raw_path.unlink(missing_ok=True)

                if (
                    playback_path is not None
                    and raw_path is not None
                    and playback_path != raw_path
                    and playback_path.exists()
                ):
                    playback_path.unlink(missing_ok=True)

                raw_path = None
                playback_path = None
                continue

            try:
                frame = frame_queue.get(timeout=0.05)
            except queue.Empty:
                if shutdown_requested_ref[0]:
                    graceful_exit_ref[0] = True
                    break
                continue
            # After playback ends, discard audio for POST_PLAYBACK_DRAIN_MS so we do not transcribe TTS echo
            if post_playback_drain_until_ts is not None:
                if time.time() < post_playback_drain_until_ts:
                    continue
                post_playback_drain_until_ts = None
                vad_monitor.set_baseline_freeze_until_ts(None)
            # After barge-in: flush mic and ignore VAD for post_playback_ignore_ms, then require fresh speech_start
            if post_playback_ignore_until_ts is not None:
                if time.time() < post_playback_ignore_until_ts:
                    continue
                post_playback_ignore_until_ts = None
                vad_monitor.set_baseline_freeze_until_ts(None)
                print("[barge-in] ready for new speech_start", flush=True)
            state = state_ref[0]
            preroll = mic.get_preroll_frames()

            rms, peak = frame_rms_peak(frame)
            rms_recent.append(rms)
            # VAD uses raw int16 bytes; meter uses same frame but does not modify it
            frame_ok_for_vad = len(frame) == VAD_BYTES_PER_FRAME
            dtype = mic.get_last_indata_dtype()
            if dtype is not None:
                try:
                    import numpy as np
                    frame_ok_for_vad = frame_ok_for_vad and (getattr(dtype, "name", None) == "int16" or dtype == np.int16)
                except ImportError:
                    pass

            if _debug_enabled():
                debug_frame_count += 1
                vad_debug_window.append(frame)
                vad_debug_rms.append(rms)
                # Once per second: indata dtype, min/max int16, len(frame_bytes), sample_rate
                now = time.time()
                if last_vad_debug_log_time is None or (now - last_vad_debug_log_time) >= 1.0:
                    last_vad_debug_log_time = now
                    min_val, max_val = _frame_min_max_int16(frame)
                    dtype_str = str(dtype) if dtype is not None else "None"
                    print(
                        f"[ambient] vad_debug indata_dtype={dtype_str} "
                        f"min={min_val} max={max_val} len(frame_bytes)={len(frame)} "
                        f"sample_rate={VAD_SAMPLE_RATE}",
                        flush=True,
                    )
                    if not frame_ok_for_vad:
                        print(
                            "[ambient] WARNING: skip VAD this frame (dtype != int16 or len != %d)" % VAD_BYTES_PER_FRAME,
                            flush=True,
                        )
                # ~1 second: level meter
                if debug_frame_count % 34 == 0:
                    print(f"[ambient] level rms={rms:.4f} peak={peak:.4f}", flush=True)
                # Every ~30 frames: speech frame count (webrtcvad OR energy)
                if debug_frame_count % 30 == 0 and len(vad_debug_window) == 30 and len(vad_debug_rms) == 30:
                    speech_count = count_speech_frames_combined(vad_debug_window, vad_debug_rms)
                    print(f"[ambient] vad= speech_frames={speech_count}/30", flush=True)
                if rms < 0.001 and peak < 0.001:
                    if last_level_time is None:
                        last_level_time = time.time()
                    else:
                        silent_seconds = time.time() - last_level_time
                        if silent_seconds > 2.0 and not silent_warning_printed:
                            print(
                                "[ambient] Mic audio appears silent; check device selection/permissions.",
                                flush=True,
                            )
                            silent_warning_printed = True
                else:
                    last_level_time = None
                    silent_seconds = 0.0
                    silent_warning_printed = False

            if state == IDLE:
                vad_start = frame_ok_for_vad and detect_speech_start(
                    preroll + [frame], current_rms=rms, current_peak=peak, log_event=False
                )
                energy_start = energy_speech_start(rms_recent, n_frames=3)
                is_vad_speech = vad_start or energy_start
                vad_start_rms = get_vad_start_rms()
                cooldown_ms = get_vad_cooldown_ms()
                now_ts = time.time()
                now_ms = int(now_ts * 1000)
                last_reject_ms = int(last_reject_ts * 1000) if last_reject_ts is not None else 0
                speech_start = should_accept_speech(
                    is_vad_speech, rms, now_ms, last_reject_ms, vad_start_rms, cooldown_ms
                )
                if is_vad_speech and not speech_start:
                    # Rejected: log one line when THREEPIO_DEBUG=1
                    if _debug_enabled():
                        reason = "low_rms" if rms < vad_start_rms else "cooldown"
                        cooldown_remaining_ms = (
                            max(0, int((reject_cooldown_until_ts - now_ts) * 1000))
                            if reject_cooldown_until_ts is not None and now_ts < reject_cooldown_until_ts
                            else 0
                        )
                        print(
                            f"[ambient] speech_start rejected reason={reason} rms={rms:.4f} threshold={vad_start_rms} "
                            f"cooldown_remaining_ms={cooldown_remaining_ms} device_index={idx} sample_rate={VAD_SAMPLE_RATE}",
                            flush=True,
                        )
                    continue
                if speech_start:
                    if cooldown_until_ts is not None and now_ts < cooldown_until_ts:
                        if last_cooldown_log_at is None or (now_ts - last_cooldown_log_at) > 1.0:
                            print("[ambient] trigger ignored (post-speech cooldown)", flush=True)
                            last_cooldown_log_at = now_ts
                    else:
                        cooldown_until_ts = None
                        last_cooldown_log_at = None
                        state = LISTENING
                        state_ref[0] = LISTENING
                        listen_frames = list(preroll) + [frame]
                        utterance_ms_acc = 0
                        silence_ms_acc = 0
                        _status("Listening...")
                        via = "webrtcvad" if vad_start else "energy"
                        print(f"[VAD] speech_start via={via} rms={rms:.4f}", flush=True)
                        if _debug_enabled():
                            print(
                                f"[ambient] speech_start accepted rms={rms:.4f} threshold={vad_start_rms} "
                                f"device_index={idx} sample_rate={VAD_SAMPLE_RATE}",
                                flush=True,
                            )
                            print("[ambient] state=LISTENING (VAD speech start)", flush=True)

            elif state == LISTENING:
                if bargein_debounce_frames > 0:
                    bargein_debounce_frames -= 1
                    continue
                if not listen_frames:
                    listen_frames = list(preroll) + [frame]
                else:
                    listen_frames.append(frame)
                if len(listen_frames) > max_listen_frames:
                    listen_frames = listen_frames[-max_listen_frames:]
                # Utterance segmentation: silence hangover or max duration → finalize once (self-healing)
                utterance_ms_acc += VAD_FRAME_MS
                vad_is_speech = rms >= get_energy_end_threshold()
                if vad_is_speech:
                    silence_ms_acc = 0
                else:
                    silence_ms_acc += VAD_FRAME_MS
                end_silence_ms = int(os.environ.get("UTTERANCE_END_SILENCE_MS", str(getattr(settings, "UTTERANCE_END_SILENCE_MS", 350))))
                max_ms = int(os.environ.get("UTTERANCE_MAX_MS", str(getattr(settings, "UTTERANCE_MAX_MS", 2500))))
                finalize_reason = None
                if utterance_ms_acc >= max_ms:
                    finalize_reason = "max_ms"
                elif silence_ms_acc >= end_silence_ms:
                    finalize_reason = "silence_hangover"
                if not finalize_reason:
                    continue
                # Finalize utterance once: run STT gate then either discard (→ IDLE) or STT → LLM (→ THINKING)
                utterance_ms = len(listen_frames) * VAD_FRAME_MS
                rms_list_utt = []
                for fb in listen_frames:
                    if len(fb) >= VAD_BYTES_PER_FRAME:
                        rms_f, _ = frame_rms_peak(fb[:VAD_BYTES_PER_FRAME])
                        rms_list_utt.append(rms_f)
                avg_rms_utt = (sum(rms_list_utt) / len(rms_list_utt)) if rms_list_utt else 0.0
                if finalize_reason == "max_ms":
                    print(f"[vad] forced_end reason=max_ms ms={utterance_ms} rms={avg_rms_utt:.4f}", flush=True)
                else:
                    print(f"[vad] end reason=silence_hangover silence_ms={silence_ms_acc} utterance_ms={utterance_ms}", flush=True)
                utterance_ms_acc = 0
                silence_ms_acc = 0
                duration_sec = len(listen_frames) * (VAD_FRAME_MS / 1000.0)
                if duration_sec < min_utterance_sec:
                    if _debug_enabled():
                        print(f"[ambient] utterance too short: {duration_sec:.2f}s < {min_utterance_sec}s, not finalizing", flush=True)
                    last_reject_ts = time.time()
                    reject_cooldown_until_ts = last_reject_ts + (get_vad_cooldown_ms() / 1000.0)
                    state = IDLE
                    state_ref[0] = IDLE
                    listen_frames = []
                    continue
                utterance_min_ms = int(os.environ.get("UTTERANCE_MIN_MS", str(getattr(settings, "UTTERANCE_MIN_MS", 450))))
                utterance_min_rms = float(os.environ.get("UTTERANCE_MIN_RMS", str(getattr(settings, "UTTERANCE_MIN_RMS", 0.010))))
                if utterance_ms < utterance_min_ms:
                    print(f'[stt-gate] discard reason=min_ms ms={utterance_ms} rms={avg_rms_utt:.4f} text=""', flush=True)
                    last_reject_ts = time.time()
                    reject_cooldown_until_ts = last_reject_ts + (get_vad_cooldown_ms() / 1000.0)
                    state = IDLE
                    state_ref[0] = IDLE
                    listen_frames = []
                    continue
                if avg_rms_utt < utterance_min_rms:
                    print(f'[stt-gate] discard reason=min_rms ms={utterance_ms} rms={avg_rms_utt:.4f} text=""', flush=True)
                    last_reject_ts = time.time()
                    reject_cooldown_until_ts = last_reject_ts + (get_vad_cooldown_ms() / 1000.0)
                    state = IDLE
                    state_ref[0] = IDLE
                    listen_frames = []
                    continue
                state = THINKING
                state_ref[0] = THINKING
                _status("Thinking...")
                print(f"[VAD] speech_end via=segmentation rms={rms:.4f}", flush=True)
                if _debug_enabled():
                    print("[ambient] state=THINKING (utterance finalize)", flush=True)
                wav_path = Path(tempfile.gettempdir()) / f"ambient_{uuid.uuid4().hex[:12]}.wav"
                try:
                    write_wav_frames(wav_path, listen_frames)
                except Exception as e:
                    logger.exception("write_wav failed")
                    _status(f"Record save failed: {e}")
                    state = IDLE
                    state_ref[0] = IDLE
                    listen_frames = []
                    continue
                try:
                    user_text, _stt_info = transcribe_wav(wav_path, settings)
                except RuntimeError as e:
                    _status(str(e))
                    state = IDLE
                    state_ref[0] = IDLE
                    listen_frames = []
                    wav_path.unlink(missing_ok=True)
                    continue
                if not user_text:
                    _status("No speech detected.")
                    state = IDLE
                    state_ref[0] = IDLE
                    listen_frames = []
                    last_reject_ts = time.time()
                    reject_cooldown_until_ts = last_reject_ts + (get_vad_cooldown_ms() / 1000.0)
                    wav_path.unlink(missing_ok=True)
                    continue
                utterance_min_words = int(os.environ.get("UTTERANCE_MIN_WORDS", str(getattr(settings, "UTTERANCE_MIN_WORDS", 2))))
                junk_str = os.environ.get("UTTERANCE_JUNK_WORDS", str(getattr(settings, "UTTERANCE_JUNK_WORDS", "you,yeah,uh,um,hmm,hey")))
                junk_set = {w.strip().lower() for w in junk_str.split(",") if w.strip()}
                words = user_text.split()
                if len(words) < utterance_min_words and user_text.strip().lower() in junk_set:
                    text_snip = (user_text[:80] or "").replace('"', "'")
                    print(f'[stt-gate] discard reason=junk_single ms={utterance_ms} rms={avg_rms_utt:.4f} text="{text_snip}"', flush=True)
                    state = IDLE
                    state_ref[0] = IDLE
                    listen_frames = []
                    last_reject_ts = time.time()
                    reject_cooldown_until_ts = last_reject_ts + (get_vad_cooldown_ms() / 1000.0)
                    wav_path.unlink(missing_ok=True)
                    continue
                # Voice ID only after STT: require real speech and minimum duration
                duration_sec = len(listen_frames) * (VAD_FRAME_MS / 1000.0)
                min_voice_sec = float(os.environ.get("THREEPIO_VOICE_MIN_SEC", "0.9"))
                speaker_identity: str | None = None
                if duration_sec >= min_voice_sec:
                    try:
                        from threepio.identity.voice_id import (
                            compute_embedding,
                            load_voiceprints,
                            match_speaker,
                        )
                        embedding = compute_embedding(wav_path)
                        voiceprints = load_voiceprints()
                        best_name, best_score, top = match_speaker(embedding, voiceprints, top_k=2)
                        if best_name:
                            speaker_identity = best_name
                        if _debug_enabled():
                            for n, s in top[:2]:
                                print(f"[ambient] voice_id top: {n!r} score={s:.4f}", flush=True)
                            print(f"[ambient] voice_id applied={speaker_identity!r} duration_sec={duration_sec:.2f}", flush=True)
                    except Exception as e:
                        logger.debug("voice_id: %s", e)
                elif _debug_enabled():
                    print(f"[ambient] voice_id skipped duration_sec={duration_sec:.2f} (min={min_voice_sec}) or no speech", flush=True)
                wav_path.unlink(missing_ok=True)
                print(f"You: {user_text}", flush=True)
                listen_frames = []

                # Build system and get reply (only final reply to TTS)
                state_obj = classify(user_text)
                profile = update_from_user_text(profile, user_text)
                if speaker_identity:
                    if hasattr(profile, "model_copy"):
                        profile = profile.model_copy(update={"name": speaker_identity})
                    else:
                        profile = {**profile, "name": speaker_identity}
                save_profile(profile, base_dir)
                if should_save_note(user_text):
                    pair = extract_note_from_user_text(user_text)
                    if pair and pair[0] is not None and pair[1] is not None:
                        add_note(pair[0], pair[1])
                addr = extract_speaker_address(profile)
                if addr is not None:
                    speaker_address = addr
                is_first = len(messages) == 0
                sys_content = build_c3po_system_prompt(profile, mode="ambient", user_text=user_text)
                now_ts = time.time()
                if get_preferred_address(profile) and should_inject_address(profile, now_ts, cooldown_s=90.0):
                    mark_addressed(profile, now_ts)
                    save_profile(profile, base_dir)
                formal_intent = interpret_user_intent(user_text)
                gloss = slang_to_formal_gloss(user_text)
                if formal_intent:
                    user_content = (
                        f"User intent (formal interpretation; do not repeat slang): {formal_intent}\n\n"
                        f"User said: {user_text}"
                    )
                elif gloss:
                    user_content = (
                        f"User slang gloss: {gloss} (do not reveal gloss unless asked)\n\n"
                        f"User: {user_text}"
                    )
                else:
                    user_content = user_text
                if not messages or messages[0].get("role") != "system":
                    messages.insert(0, {"role": "system", "content": sys_content})
                else:
                    messages[0] = {"role": "system", "content": sys_content}
                messages.append({"role": "user", "content": user_content})
                _deflect = (
                    getattr(state_obj, "name", None) == "DEFLECT"
                    or (isinstance(state_obj, dict) and not state_obj.get("allow", True))
                )
                if _deflect:
                    reply = "I am afraid I must remain in character as C-3PO."
                else:
                    try:
                        reply = generate_reply(messages, client=llm_client)
                    except Exception as e:
                        _status(f"LLM failed: {e}")
                        messages.pop()
                        state = IDLE
                        state_ref[0] = IDLE
                        continue
                if _debug_enabled():
                    print("[LLM] requests_this_turn=1", flush=True)
                messages.append({"role": "assistant", "content": reply})
                # Keep system + last 10 user/assistant pairs
                max_turns = 10
                while len(messages) > 1 + max_turns * 2:
                    # Drop oldest user or assistant message (keep system at 0)
                    if len(messages) > 1:
                        messages.pop(1)
                cleaned = apply_echo_guard(user_text, reply)
                display_text, speech_text = shape_for_speech(cleaned)
                print(f"C-3PO: {display_text}", flush=True)

                # Synthesize and apply FX (same pipeline as main, no echo)
                out_dir = Path("data/tts")
                out_dir.mkdir(parents=True, exist_ok=True)
                ext = ".mp3"
                raw_path = out_dir / f"ambient_{uuid.uuid4().hex[:12]}{ext}"
                try:
                    synthesize_to_file(tts, speech_text, str(raw_path))
                except Exception as e:
                    _status(f"TTS failed: {e}")
                    state = IDLE
                    state_ref[0] = IDLE
                    continue
                playback_path = raw_path
                enable_fx = getattr(settings, "ENABLE_C3PO_FX", False)
                if not enable_fx:
                    logger.debug("[fx] skipped (reason=disabled)")
                else:
                    if not ffmpeg_checked_ref[0]:
                        import shutil
                        ffmpeg_checked_ref[0] = True
                        ffmpeg_available_ref[0] = bool(shutil.which("ffmpeg"))
                        if not ffmpeg_available_ref[0]:
                            _status("ffmpeg not found. Install: brew install ffmpeg (macOS) or apt install ffmpeg (Linux). Set ENABLE_C3PO_FX=false to skip.")
                    if not ffmpeg_available_ref[0]:
                        logger.debug("[fx] skipped (reason=missing_ffmpeg)")
                    else:
                        logger.debug("[fx] applying")
                        from threepio.speech.tts.c3po_fx import apply_c3po_fx
                        processed = out_dir / f"ambient_fx_{uuid.uuid4().hex[:12]}.wav"
                        try:
                            apply_c3po_fx(str(raw_path), str(processed))
                            playback_path = processed
                        except Exception as e:
                            logger.warning("[fx] skipped (reason=missing_fx_chain or error): %s", e)
                state = SPEAKING
                state_ref[0] = SPEAKING
                barge_in_mode = (os.environ.get("BARGE_IN_MODE") or getattr(settings, "BARGE_IN_MODE", "full") or "full").strip().lower()
                print(f"[barge-in] mode={barge_in_mode}", flush=True)
                if barge_in_mode in ("off", "assisted"):
                    print(f"[barge-in] playback mic_processing=disabled reason={barge_in_mode}", flush=True)
                _status("Speaking...")
                if _debug_enabled():
                    print("[ambient] state=SPEAKING", flush=True)
                # Suppression at exact moment playback starts: no barge-in / VAD finalization for THREEPIO_SPEECH_SUPPRESS_MS
                vad_monitor.set_mode("barge_in")
                _bf = vad_monitor.get_baseline_rms()
                _floor = get_barge_in_baseline_floor()
                baseline_freeze_rms_ref[0] = max(_bf, _floor) if _bf is not None else None
                if baseline_freeze_rms_ref[0] is not None:
                    print(f"[barge-in] baseline_freeze start={baseline_freeze_rms_ref[0]:.4f}", flush=True)
                suppress_ms = get_speech_suppress_ms()
                pcm = _decode_audio_to_pcm_16k(playback_path)
                t0 = time.time()
                _corr_win = int(os.environ.get("BARGE_IN_CORR_WINDOW_MS", str(getattr(settings, "BARGE_IN_CORR_WINDOW_MS", 200))))
                _corr_sweep = int(os.environ.get("BARGE_IN_CORR_LAG_SWEEP_MS", str(getattr(settings, "BARGE_IN_CORR_LAG_SWEEP_MS", 60))))
                _N = int(CORR_SAMPLE_RATE * _corr_win / 1000)
                _sweep = int(CORR_SAMPLE_RATE * _corr_sweep / 1000)
                _spk_need = _N + 2 * _sweep
                print(
                    f"[barge-in] corr_debug mic_sr={CORR_SAMPLE_RATE} spk_sr={CORR_SAMPLE_RATE} N={_N} sweep={_sweep} mic_required={_N} spk_required={_spk_need}",
                    flush=True,
                )
                with speaker_lock:
                    speaker_pcm_ref[0] = pcm if getattr(pcm, "size", 0) > 0 else None
                    playback_start_ts_ref[0] = t0
                vad_monitor.set_speaking_start_ts(t0)
                _status(f"speaking suppression active for {suppress_ms} ms")
                handle = play_audio_file_interruptible(playback_path)
                if handle is None:
                    _status(NO_PLAYER_MESSAGE)
                    state = IDLE
                    state_ref[0] = IDLE
                    baseline_freeze_rms_ref[0] = None
                    corr_echo_samples_ref[0] = []
                    corr_echo_ref[0] = None
                    continue
                handle_ref[0] = handle
                continue

    except KeyboardInterrupt:
        graceful_exit_ref[0] = True
        _status("Stopping.")
    finally:
        logger.info("Shutdown: stopping playback")
        print("[ambient] shutdown: stopping playback...", flush=True)
        h = handle_ref[0]
        if h is not None and h.is_running():
            h.stop()
            handle_ref[0] = None
        logger.info("Shutdown: stopping VAD monitor")
        print("[ambient] shutdown: stopping VAD monitor...", flush=True)
        try:
            vad_monitor.stop()
        except Exception as e:
            logger.debug("vad_monitor.stop: %s", e)
        logger.info("Shutdown: closing mic stream")
        print("[ambient] shutdown: closing mic stream...", flush=True)
        mic.stop()
        logger.info("Shutdown complete")
        print("[ambient] shutdown complete.", flush=True)
    return 0 if graceful_exit_ref[0] else 1
