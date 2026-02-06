"""Voice mode orchestration: OpenAI Realtime API with mock/mic input."""

import asyncio
import base64
import logging
import sys
from typing import NoReturn

from threepio.config import get_settings
from threepio.eyes.controller import EyesController
from threepio.runtime.lifecycle import LifecycleManager
from threepio.runtime.state import SystemState
from threepio.runtime.log import setup_runtime_logging

logger = logging.getLogger(__name__)


def _get_audio_output():
    """Create audio output from settings."""
    from threepio.audio.output import PrintOutput, PlayOutput
    settings = get_settings()
    if settings.AUDIO_OUTPUT_MODE == "print":
        return PrintOutput()
    out = PlayOutput(sr=settings.REALTIME_SAMPLE_RATE, device=settings.AUDIO_OUTPUT_DEVICE)
    out.start()
    return out


def _get_audio_input():
    """Create audio input; fall back to mock if mic unavailable."""
    from threepio.audio.input import MicInput, MockInput
    settings = get_settings()
    if settings.AUDIO_INPUT_MODE == "mic":
        try:
            return MicInput(
                sr=settings.REALTIME_SAMPLE_RATE,
                frame_ms=settings.REALTIME_FRAME_MS,
                device=settings.AUDIO_INPUT_DEVICE,
            )
        except ImportError:
            logger.warning("AUDIO_INPUT_MODE=mic but sounddevice not installed, using mock")
    return MockInput()


def _is_mock_input(obj) -> bool:
    """True if input adapter is MockInput (typed lines)."""
    return hasattr(obj, "utterances")


async def _run_voice_loop() -> None:
    """Main async voice loop."""
    settings = get_settings()
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        print("OPENAI_API_KEY required for realtime voice. Set it or use PROVIDER_VOICE=cli.")
        return

    from threepio.voice.realtime_client import RealtimeVoiceClient

    lifecycle = LifecycleManager()
    eyes = EyesController()
    lifecycle.register_cleanup(eyes.shutdown)

    client = RealtimeVoiceClient(api_key=api_key, model=settings.REALTIME_MODEL)
    output = _get_audio_output()
    input_adapter = _get_audio_input()

    lifecycle.set_state(SystemState.BOOTING)
    eyes.start()
    await client.connect()
    await client.session_update(voice=settings.REALTIME_VOICE)
    lifecycle.set_state(SystemState.IDLE)

    mock_input = _is_mock_input(input_adapter)
    partial_text: list[str] = []
    state = SystemState.IDLE

    async def process_events():
        nonlocal partial_text, state
        async for ev in client.events():
            t = ev.get("type", "")
            if t == "response.text.delta":
                delta = ev.get("delta", "")
                if delta:
                    partial_text.append(delta)
                    if mock_input:
                        print(delta, end="", flush=True)
            elif t == "response.audio.delta":
                state = SystemState.SPEAKING
                b64 = ev.get("delta", "")
                if b64:
                    chunk = base64.b64decode(b64)
                    output.play(chunk)
            elif t == "response.done":
                if partial_text and mock_input:
                    print()
                partial_text.clear()
                state = SystemState.IDLE
                break
            elif t == "input_audio_buffer.committed":
                if state == SystemState.SPEAKING:
                    output.stop()
                    await client.cancel_response()
                state = SystemState.THINKING
                await client.request_response()

    if mock_input:
        print("THREEPIO voice (mock). Type your message and press Enter. Type 'quit' to exit.\n")
        async for ut in input_adapter.utterances():
            if ut.text is None:
                continue
            lifecycle.set_state(SystemState.LISTENING)
            await client.send_text(ut.text)
            await client.request_response()
            lifecycle.set_state(SystemState.THINKING)
            await process_events()
            lifecycle.set_state(SystemState.IDLE)
    else:
        print("THREEPIO voice (mic). Speak, or Ctrl+C to exit.\n")
        mic_state = SystemState.IDLE

        async def mic_stream():
            async for frame in input_adapter.frames():
                await client.send_audio_frame(frame)

        async def recv_loop():
            nonlocal partial_text, mic_state
            async for ev in client.events():
                t = ev.get("type", "")
                if t == "response.text.delta":
                    delta = ev.get("delta", "")
                    if delta:
                        partial_text.append(delta)
                        print(delta, end="", flush=True)
                elif t == "response.audio.delta":
                    mic_state = SystemState.SPEAKING
                    b64 = ev.get("delta", "")
                    if b64:
                        output.play(base64.b64decode(b64))
                elif t == "response.done":
                    if partial_text:
                        print()
                    partial_text.clear()
                    mic_state = SystemState.IDLE
                elif t == "input_audio_buffer.committed":
                    if mic_state == SystemState.SPEAKING:
                        output.stop()
                        await client.cancel_response()
                    mic_state = SystemState.THINKING
                    await client.request_response()

        mic_task = asyncio.create_task(mic_stream())
        recv_task = asyncio.create_task(recv_loop())
        try:
            await asyncio.gather(mic_task, recv_task)
        except asyncio.CancelledError:
            mic_task.cancel()
            recv_task.cancel()

    await client.close()
    lifecycle.run_cleanup()
    print("\nGoodbye!")


def run() -> NoReturn:
    """Entry point for voice mode."""
    try:
        asyncio.run(_run_voice_loop())
    except KeyboardInterrupt:
        logger.info("Interrupted")
    sys.exit(0)
