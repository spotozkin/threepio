"""Microphone capture with pre-roll ring buffer. Mono 16 kHz PCM int16."""

from __future__ import annotations

import logging
import os
import struct
import threading
from collections import deque
from pathlib import Path
from queue import Empty, Queue
from typing import Any

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
BYTES_PER_SAMPLE = 2

# Pre-roll: last 300ms. At 16kHz, 300ms = 4800 samples = 9600 bytes.
# Frame size for VAD (webrtcvad): 10/20/30 ms at 16kHz. We use 30ms = 480 samples = 960 bytes.
FRAME_MS = 30
SAMPLES_PER_FRAME = int(SAMPLE_RATE * FRAME_MS / 1000)
BYTES_PER_FRAME = SAMPLES_PER_FRAME * BYTES_PER_SAMPLE
PRE_ROLL_MS = 300
PRE_ROLL_FRAMES = PRE_ROLL_MS // FRAME_MS  # 10 frames


def _device_info_from_query(sd: Any, device_index: int) -> tuple[str, int, float | None]:
    """Query device by integer index; return (name, max_input_channels, default_samplerate)."""
    try:
        info = sd.query_devices(int(device_index))
    except Exception:
        return (str(device_index), 0, None)
    name = getattr(info, "name", None)
    if name is None:
        name = str(device_index)
    else:
        name = str(name).strip() or str(device_index)
    max_in = getattr(info, "max_input_channels", 0)
    try:
        max_in = int(max_in)
    except (TypeError, ValueError):
        max_in = 0
    default_sr = getattr(info, "default_samplerate", None)
    if default_sr is not None:
        try:
            default_sr = float(default_sr)
        except (TypeError, ValueError):
            default_sr = None
    return (name, max_in, default_sr)


def resolve_audio_input_device(raw_override: str | None = None) -> tuple[int | None, str]:
    """
    Resolve to (device_index, device_name). Uses THREEPIO_AUDIO_INPUT_DEVICE unless
    raw_override is provided.
    - Numeric string (e.g. "1", "3"): treat as integer device index; name from query_devices(idx).
    - Non-numeric string: substring match on device name (case-insensitive); only consider
      devices with max_input_channels > 0; first match wins.
    - Unset/empty: use default input device.
    Always returns (int | None, str). When found, device_index is an int for use with
    query_devices(resolved_index) and InputStream(device=resolved_index).
    """
    try:
        import sounddevice as sd
    except ImportError:
        return (None, "<default (sounddevice not loaded)>")

    raw = raw_override if raw_override is not None else os.environ.get("THREEPIO_AUDIO_INPUT_DEVICE", "").strip()
    if not raw:
        try:
            default = sd.default.device[0]
            default = int(default)
            name, _, _ = _device_info_from_query(sd, default)
            return (default, name)
        except Exception:
            return (None, "<default>")

    # Numeric string → integer device index
    if raw.strip().isdigit():
        try:
            idx = int(raw)
            name, _, _ = _device_info_from_query(sd, idx)
            return (idx, name)
        except Exception:
            return (None, "<invalid index?>")

    # Non-numeric: substring match on device names; only input-capable devices (max_input_channels > 0)
    sub = raw.lower()
    try:
        devices = sd.query_devices()
        try:
            devices = list(devices)
        except Exception:
            devices = [devices]
        for i, dev in enumerate(devices):
            max_in = getattr(dev, "max_input_channels", 0)
            try:
                max_in = int(max_in)
            except (TypeError, ValueError):
                max_in = 0
            if max_in <= 0:
                continue
            dev_name = getattr(dev, "name", None) or ""
            dev_name = (dev_name or "").strip()
            if not dev_name:
                continue
            if sub in dev_name.lower():
                name = dev_name or f"device {i}"
                return (int(i), name)
    except Exception as e:
        logger.debug("resolve_audio_input_device list: %s", e)
    return (None, f"<no match for '{raw}'>")


def frame_rms_peak(frame: bytes) -> tuple[float, float]:
    """Return (rms, peak) for int16 PCM frame, normalized 0..1 (peak 1.0 = 32767)."""
    if not frame or len(frame) < 2:
        return (0.0, 0.0)
    n = len(frame) // 2
    try:
        samples = struct.unpack(f"<{n}h", frame[: n * 2])
    except struct.error:
        return (0.0, 0.0)
    if not samples:
        return (0.0, 0.0)
    peak = max(abs(s) for s in samples)
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
    return (rms / 32768.0, peak / 32768.0)


class MicStream:
    """Capture mono 16 kHz PCM via sounddevice.InputStream; pre-roll ring buffer. Frames are exactly BYTES_PER_FRAME (960) for VAD."""

    def __init__(self, device: int | None = None, block_duration_ms: int = FRAME_MS) -> None:
        self._device = device  # int or None for default
        self._block_duration_ms = block_duration_ms
        self._block_size = int(SAMPLE_RATE * block_duration_ms / 1000) * BYTES_PER_SAMPLE  # 960 for 30ms
        self._blocksize_samples = self._block_size // BYTES_PER_SAMPLE  # 480 for 30ms
        self._ring: deque[bytes] = deque(maxlen=PRE_ROLL_FRAMES)
        self._lock = threading.Lock()
        self._stream = None
        self._running = False
        self._device_info: dict[str, Any] = {}
        self._frame_queue: Queue[bytes] = Queue()
        self._last_indata_dtype: Any = None

    def _audio_callback(self, indata: Any, frames: int, time: Any, status: Any) -> None:
        """Callback for sounddevice.InputStream: build int16 mono bytes (exactly BYTES_PER_FRAME) and put in queue."""
        import numpy as np
        self._last_indata_dtype = getattr(indata, "dtype", None)
        arr = np.asarray(indata).reshape(-1)
        if arr.dtype != np.int16:
            # Some backends (e.g. macOS) may give float; convert -1..1 to int16
            arr = (np.clip(arr.astype(np.float64), -1.0, 1.0) * 32767).astype(np.int16)
        else:
            arr = arr.astype(np.int16, copy=False)
        frame_bytes = arr.tobytes()
        if len(frame_bytes) > BYTES_PER_FRAME:
            frame_bytes = frame_bytes[:BYTES_PER_FRAME]
        elif len(frame_bytes) < BYTES_PER_FRAME:
            frame_bytes = frame_bytes.ljust(BYTES_PER_FRAME, b"\x00")
        try:
            self._frame_queue.put_nowait(frame_bytes)
        except Exception:
            pass

    def _get_stream(self):
        """Lazy-init capture stream: sounddevice.InputStream with device=resolved int, 16kHz mono int16, blocksize 480."""
        if self._stream is not None:
            return self._stream
        try:
            import sounddevice as sd
            import numpy as np
        except ImportError as e:
            raise RuntimeError("Mic capture requires sounddevice and numpy. pip install sounddevice numpy") from e
        dev = self._device
        if dev is None:
            dev = sd.default.device[0]
        try:
            dev = int(dev)
        except (TypeError, ValueError):
            dev = int(sd.default.device[0])
        self._device = dev
        # Query device with integer index for accurate name, max_input_channels, default_samplerate
        name, max_ch, default_sr = _device_info_from_query(sd, dev)
        self._device_info = {
            "device_index": dev,
            "device_name": name,
            "max_input_channels": max_ch,
            "default_samplerate": default_sr,
            "sample_rate": SAMPLE_RATE,
            "dtype": DTYPE,
            "channels": CHANNELS,
            "frames_per_buffer": self._blocksize_samples,
            "frame_duration_ms": self._block_duration_ms,
        }
        # InputStream: known-good format for VAD (mono 16kHz int16, 30ms frames); device=int
        stream = sd.InputStream(
            device=dev,
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=self._blocksize_samples,
            callback=self._audio_callback,
        )
        self._stream = stream
        logger.debug("[mic_stream] using sounddevice InputStream")
        return self._stream

    def get_device_info(self) -> dict[str, Any]:
        """Return device info (after start). Includes device_index, device_name, max_input_channels, default_samplerate, sample_rate, ..."""
        if not self._device_info and self._stream is None:
            self._get_stream()
        return dict(self._device_info)

    def get_last_indata_dtype(self) -> Any:
        """Last indata.dtype seen in the capture callback (for THREEPIO_DEBUG validation)."""
        return self._last_indata_dtype

    def start(self) -> None:
        """Start capture; callback will push frames into queue."""
        stream = self._get_stream()
        stream.start()
        self._running = True
        logger.debug("[mic_stream] started")

    def stop(self) -> None:
        """Stop capture."""
        self._running = False
        if self._stream is not None and hasattr(self._stream, "stop"):
            try:
                self._stream.stop()
            except Exception:
                pass
        logger.debug("[mic_stream] stopped")

    def read_frame(self) -> bytes | None:
        """Read one frame (block_duration_ms). Returns None if stopped. Exactly BYTES_PER_FRAME bytes, mono 16kHz int16."""
        if not self._running:
            return None
        try:
            frame = self._frame_queue.get(timeout=0.5)
            with self._lock:
                self._ring.append(frame)
            return frame
        except Empty:
            return None
        except Exception as e:
            if self._running:
                logger.debug("[mic_stream] read error: %s", e)
            return None

    def get_preroll_frames(self) -> list[bytes]:
        """Return list of frames in the pre-roll buffer (last PRE_ROLL_MS)."""
        with self._lock:
            return list(self._ring)


def write_wav(path: str | Path, frames: list[bytes], sample_rate: int = SAMPLE_RATE) -> Path:
    """Write PCM frames to a WAV file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    import wave
    data = b"".join(frames)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(BYTES_PER_SAMPLE)
        wav.setframerate(sample_rate)
        wav.writeframes(data)
    return path
