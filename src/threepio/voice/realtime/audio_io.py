"""Audio I/O for realtime: mic input and speaker output."""

import asyncio
import logging
import queue
import threading
from typing import AsyncIterator, Iterator

logger = logging.getLogger(__name__)

_MOCK = False
_np = None
try:
    import numpy as _np
    import sounddevice as sd
except ImportError:
    _MOCK = True


class MicrophoneStream:
    """Yields PCM16 frames at FRAME_MS intervals. Mock mode logs when sounddevice unavailable."""

    def __init__(self, sr: int, frame_ms: int, device: int | str | None = None) -> None:
        self._sr = sr
        self._frame_ms = frame_ms
        self._device = device
        self._frame_samples = int(sr * frame_ms / 1000)
        self._frame_bytes = self._frame_samples * 2  # 16-bit

    def __iter__(self) -> Iterator[bytes]:
        if _MOCK:
            logger.warning("[AUDIO] MicrophoneStream: mock mode (sounddevice not available)")
            while True:
                yield b"\x00" * self._frame_bytes
        try:
            with sd.InputStream(
                samplerate=self._sr,
                channels=1,
                dtype="int16",
                blocksize=self._frame_samples,
                device=self._device,
            ) as stream:
                while True:
                    data, _ = stream.read(self._frame_samples)
                    yield data.tobytes()
        except Exception as e:
            logger.error("[AUDIO] MicrophoneStream failed: %s", e)
            raise

    async def aiter(self) -> AsyncIterator[bytes]:
        """Async iterator for mic frames."""
        if _MOCK:
            logger.warning("[AUDIO] MicrophoneStream: mock mode (sounddevice not available)")
            while True:
                await asyncio.sleep(self._frame_ms / 1000.0)
                yield b"\x00" * self._frame_bytes
            return
        q: asyncio.Queue[bytes] = asyncio.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                logger.warning("[AUDIO] Mic status: %s", status)
            try:
                q.put_nowait(indata.tobytes())
            except asyncio.QueueFull:
                pass

        with sd.InputStream(
            samplerate=self._sr,
            channels=1,
            dtype="int16",
            blocksize=self._frame_samples,
            device=self._device,
            callback=callback,
        ):
            while True:
                yield await q.get()


class SpeakerStream:
    """Plays PCM16 frames ASAP. Mock mode logs when sounddevice unavailable."""

    def __init__(self, sr: int, device: int | str | None = None) -> None:
        self._sr = sr
        self._device = device
        self._queue: queue.Queue[bytes] = queue.Queue()
        self._playing = False

    def play(self, pcm16_bytes: bytes) -> None:
        """Queue audio for playback."""
        if _MOCK:
            logger.debug("[AUDIO] SpeakerStream: mock mode, would play %d bytes", len(pcm16_bytes))
            return
        self._queue.put(pcm16_bytes)

    def flush(self) -> None:
        """Clear queued audio (for barge-in)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        logger.debug("[AUDIO] SpeakerStream flushed")

    def start_playback_loop(self) -> None:
        """Start background thread that plays queued audio."""
        if _MOCK:
            return

        def _play():
            self._playing = True
            while self._playing:
                try:
                    data = self._queue.get(timeout=0.1)
                    arr = _np.frombuffer(data, dtype="int16")
                    sd.play(arr, self._sr, device=self._device, blocking=True)
                except queue.Empty:
                    continue
                except Exception as e:
                    logger.exception("[AUDIO] Playback error: %s", e)

        t = threading.Thread(target=_play, daemon=True)
        t.start()

    def stop(self) -> None:
        """Stop playback loop."""
        self._playing = False
