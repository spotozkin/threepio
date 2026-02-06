"""OpenAI Realtime API WebSocket client."""

import asyncio
import base64
import inspect
import json
import logging
import ssl
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

REALTIME_URL = "wss://api.openai.com/v1/realtime"


def _ssl_context() -> ssl.SSLContext:
    """Create SSL context; prefer certifi CA bundle if available."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        logger.warning(
            "certifi not installed; using default CA bundle. "
            "For macOS Python 3.13, install certifi to fix CERTIFICATE_VERIFY_FAILED."
        )
        return ssl.create_default_context()


def _websockets_connect_params() -> set[str]:
    """Return parameter names accepted by websockets.connect (header kwarg compat)."""
    import websockets
    return set(inspect.signature(websockets.connect).parameters)


class AsyncRealtimeClient:
    """Async WebSocket client for OpenAI Realtime API."""

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._ws = None
        self._receive_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Open WebSocket connection."""
        import websockets
        url = f"{REALTIME_URL}?model={self._model}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        kwargs: dict[str, Any] = {
            "ping_interval": 20,
            "ping_timeout": 10,
            "ssl": _ssl_context(),
        }
        if "additional_headers" in _websockets_connect_params():
            kwargs["additional_headers"] = headers
        else:
            kwargs["extra_headers"] = headers
        self._ws = await websockets.connect(url, **kwargs)
        logger.info("Connected to OpenAI Realtime API")

    async def _send(self, event: dict[str, Any]) -> None:
        """Send JSON event."""
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        try:
            await self._ws.send(json.dumps(event))
        except Exception as e:
            from websockets.exceptions import ConnectionClosed
            if isinstance(e, ConnectionClosed):
                raise RuntimeError("WebSocket connection closed unexpectedly") from e
            raise

    async def start_session(
        self,
        instructions: str,
        voice: str,
        model: str | None = None,
        tools: list[dict] | None = None,
    ) -> None:
        """Configure session (instructions, voice)."""
        session: dict[str, Any] = {
            "modalities": ["text", "audio"],
            "instructions": instructions,
            "voice": voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "input_audio_transcription": {"model": "whisper-1"},
            "turn_detection": {"type": "server_vad", "threshold": 0.5, "prefix_padding_ms": 300, "silence_duration_ms": 500},
        }
        if tools:
            session["tools"] = tools
        await self._send({"type": "session.update", "session": session})

    async def send_audio_frame(self, pcm16_bytes: bytes) -> None:
        """Append PCM16 audio to input buffer (base64 encoded)."""
        b64 = base64.b64encode(pcm16_bytes).decode("ascii")
        await self._send({"type": "input_audio_buffer.append", "audio": b64})

    async def interrupt(self) -> None:
        """Cancel current output (barge-in)."""
        await self._send({"type": "response.cancel"})
        await self._send({"type": "input_audio_buffer.clear"})
        logger.debug("Interrupt sent")

    async def receive_loop(
        self,
        on_audio_chunk: Callable[[bytes], Awaitable[None] | None],
        on_text_delta: Callable[[str], Awaitable[None] | None] | None = None,
        on_event: Callable[[dict], Awaitable[None] | None] | None = None,
    ) -> None:
        """Process incoming messages. Runs until connection closes."""
        if not self._ws:
            return
        async for msg in self._ws:
            try:
                data = json.loads(msg)
                t = data.get("type", "")

                if t == "response.audio.delta":
                    audio_b64 = data.get("delta", "")
                    if audio_b64:
                        chunk = base64.b64decode(audio_b64)
                        if asyncio.iscoroutinefunction(on_audio_chunk):
                            await on_audio_chunk(chunk)
                        else:
                            on_audio_chunk(chunk)

                elif t == "conversation.item.input_audio_transcription.completed" and on_text_delta:
                    transcript = data.get("transcript", "")
                    if transcript:
                        if asyncio.iscoroutinefunction(on_text_delta):
                            await on_text_delta(transcript)
                        else:
                            on_text_delta(transcript)

                if on_event:
                    if asyncio.iscoroutinefunction(on_event):
                        await on_event(data)
                    else:
                        on_event(data)
            except Exception as e:
                logger.exception("Error processing message: %s", e)

    async def close(self) -> None:
        """Close WebSocket connection."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug("Error closing WebSocket: %s", e)
            self._ws = None
        logger.info("Realtime client closed")
