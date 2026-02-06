"""Run realtime voice agent (streaming, barge-in)."""

import asyncio
import logging
import signal
import sys

from threepio.config import get_settings
from threepio.eyes.controller import EyesController

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "You are C-3PO, a polite protocol droid. Be helpful, formal, and slightly anxious. "
    "Keep responses concise. You can answer questions about time, weather, and stocks."
)
BARGE_IN_ENERGY_THRESHOLD = 0.02  # RMS threshold for barge-in


def _rms(pcm16_bytes: bytes) -> float:
    """Compute RMS of PCM16 mono."""
    n = len(pcm16_bytes) // 2
    if n == 0:
        return 0.0
    total = 0
    for i in range(0, len(pcm16_bytes), 2):
        s = int.from_bytes(pcm16_bytes[i : i + 2], "little", signed=True)
        total += s * s
    return (total / n) ** 0.5 / 32768.0


async def run_realtime_voice_agent() -> None:
    """Run OpenAI Realtime voice agent with eyes, mic, speaker, barge-in."""
    try:
        from threepio.voice.realtime.audio_io import MicrophoneStream, SpeakerStream
        from threepio.voice.realtime.client import AsyncRealtimeClient
    except ImportError as e:
        logger.error("Realtime dependencies not installed (%s). Run: pip install -e '.[realtime]'", e)
        raise

    settings = get_settings()
    eyes = EyesController()
    eyes.start()

    client = AsyncRealtimeClient(api_key=settings.OPENAI_API_KEY or "", model=settings.REALTIME_MODEL)
    await client.connect()
    await client.start_session(
        instructions=INSTRUCTIONS,
        voice=settings.REALTIME_VOICE,
        model=settings.REALTIME_MODEL,
    )

    sr = settings.REALTIME_SAMPLE_RATE
    frame_ms = settings.REALTIME_FRAME_MS
    mic = MicrophoneStream(sr, frame_ms, settings.AUDIO_INPUT_DEVICE)
    speaker = SpeakerStream(sr, settings.AUDIO_OUTPUT_DEVICE)
    speaker.start_playback_loop()

    speaking = asyncio.Event()

    async def on_audio(chunk: bytes) -> None:
        speaker.play(chunk)

    async def mic_sender() -> None:
        async for frame in mic.aiter():
            await client.send_audio_frame(frame)
            rms = _rms(frame)
            if speaking.is_set() and rms > BARGE_IN_ENERGY_THRESHOLD:
                await client.interrupt()
                speaker.flush()
                speaking.clear()

    async def receive_loop() -> None:
        async def on_event(ev: dict) -> None:
            t = ev.get("type", "")
            if t == "response.audio.delta":
                speaking.set()
            elif t in ("response.done", "response.audio.done"):
                speaking.clear()

        await client.receive_loop(on_audio_chunk=on_audio, on_event=on_event)

    loop = asyncio.get_running_loop()
    mic_task = asyncio.create_task(mic_sender())
    recv_task = asyncio.create_task(receive_loop())

    def shutdown(*args: object) -> None:
        logger.info("Shutdown requested")
        mic_task.cancel()
        recv_task.cancel()

    try:
        loop.add_signal_handler(signal.SIGINT, shutdown)
        loop.add_signal_handler(signal.SIGTERM, shutdown)
    except OSError:
        pass

    try:
        await asyncio.gather(mic_task, recv_task)
    except asyncio.CancelledError:
        pass
    finally:
        await client.close()
        speaker.stop()
        eyes.shutdown()


def run_realtime_sync() -> None:
    """Synchronous entry: run async realtime agent."""
    from threepio.runtime.log import setup_runtime_logging
    settings = get_settings()
    setup_runtime_logging(level=settings.LOG_LEVEL)
    try:
        asyncio.run(run_realtime_voice_agent())
    except KeyboardInterrupt:
        pass
    print("\nGoodbye!")
