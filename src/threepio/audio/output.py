"""Audio output: play or print, with stop() for interruption."""

import logging
import queue
import tempfile
import threading
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

HAS_SOUNDDEVICE = False
try:
    import numpy as np
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    pass


class AudioOutput(ABC):
    """Abstract audio output with stop() for barge-in."""

    @abstractmethod
    def play(self, pcm16_bytes: bytes) -> None:
        """Play PCM16 audio."""

    @abstractmethod
    def stop(self) -> None:
        """Stop playback and flush buffer (for barge-in)."""


class PrintOutput(AudioOutput):
    """Log audio bytes (dev-friendly, no headphones)."""

    def __init__(self) -> None:
        self._playing = False

    def play(self, pcm16_bytes: bytes) -> None:
        self._playing = True
        logger.debug("[Audio] %d bytes (PCM16)", len(pcm16_bytes))
        print(f"[Audio] {len(pcm16_bytes)} bytes")

    def stop(self) -> None:
        self._playing = False
        logger.debug("[Audio] stopped")


class PlayOutput(AudioOutput):
    """Play PCM16 via sounddevice or, when unavailable, via cross-platform file playback (ffplay/aplay/mpg123)."""

    def __init__(self, sr: int = 24000, device: int | str | None = None) -> None:
        self._sr = sr
        self._device = device
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._playing = False
        self._thread: threading.Thread | None = None

    def play(self, pcm16_bytes: bytes) -> None:
        self._queue.put(pcm16_bytes)

    def stop(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._playing = False
        logger.debug("[Audio] stopped (buffer flushed)")

    def _run(self) -> None:
        self._playing = True
        while self._playing:
            try:
                data = self._queue.get(timeout=0.1)
                if HAS_SOUNDDEVICE:
                    arr = np.frombuffer(data, dtype="int16")
                    sd.play(arr, self._sr, device=self._device, blocking=True)
                else:
                    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                        path = Path(f.name)
                        self._write_wav(path, data)
                    try:
                        from threepio.speech.playback import play_file
                        play_file(path)
                    finally:
                        path.unlink(missing_ok=True)
            except queue.Empty:
                continue
            except Exception as e:
                logger.exception("[Audio] playback error: %s", e)

    def _write_wav(self, path: Path, data: bytes) -> None:
        import wave
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(self._sr)
            w.writeframes(data)

    def start(self) -> None:
        """Start playback thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
