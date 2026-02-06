"""Audio input: mic or mock (typed lines)."""

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator

logger = logging.getLogger(__name__)

HAS_SOUNDDEVICE = False
try:
    import sounddevice as sd
    HAS_SOUNDDEVICE = True
except ImportError:
    pass


@dataclass
class UtteranceEvent:
    """User utterance (text or audio)."""

    text: str | None = None
    audio_bytes: bytes | None = None


class MicInput:
    """Capture 24kHz mono PCM16 from microphone (Realtime API). Requires sounddevice."""

    def __init__(self, sr: int = 24000, frame_ms: int = 20, device: int | str | None = None) -> None:
        if not HAS_SOUNDDEVICE:
            raise ImportError("MicInput requires sounddevice. Run: pip install -e '.[realtime]'")
        self._sr = sr
        self._frame_samples = int(sr * frame_ms / 1000)
        self._device = device

    async def frames(self) -> AsyncIterator[bytes]:
        """Yield PCM16 frames."""
        q: asyncio.Queue[bytes] = asyncio.Queue()

        def callback(indata, frames, time_info, status):
            if status:
                logger.warning("[Mic] status: %s", status)
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


class MockInput:
    """Produce utterance events from typed lines (no audio)."""

    async def utterances(self) -> AsyncIterator[UtteranceEvent]:
        """Yield utterance events from console input."""
        loop = asyncio.get_event_loop()
        while True:
            try:
                line = await loop.run_in_executor(None, lambda: input("You: ").strip())
            except EOFError:
                break
            if line.lower() == "quit":
                break
            if line:
                yield UtteranceEvent(text=line)
