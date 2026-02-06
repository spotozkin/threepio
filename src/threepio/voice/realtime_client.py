"""OpenAI Realtime API WebSocket client."""

import base64
import inspect
import json
import logging
import ssl
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)

REALTIME_WS_URL = "wss://api.openai.com/v1/realtime"


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
    """Return parameter names accepted by websockets.connect (for header kwarg compat)."""
    import websockets
    sig = inspect.signature(websockets.connect)
    return set(sig.parameters)


class RealtimeVoiceClient:
    """WebSocket client for OpenAI Realtime API."""

    def __init__(self, api_key: str, model: str) -> None:
        try:
            import websockets
        except ImportError as err:
            raise ImportError(
                "Realtime voice requires websockets. Run: pip install -e '.[realtime]'"
            ) from err
        self._api_key = api_key
        self._model = model
        self._ws = None

    async def connect(self) -> None:
        """Open WebSocket connection."""
        import websockets

        url = f"{REALTIME_WS_URL}?model={self._model}"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        kwargs: dict[str, Any] = {
            "ping_interval": 20,
            "ping_timeout": 10,
            "ssl": _ssl_context(),
        }

        # websockets 16+ uses additional_headers; older versions use extra_headers
        if "additional_headers" in _websockets_connect_params():
            kwargs["additional_headers"] = headers
        else:
            kwargs["extra_headers"] = headers

        self._ws = await websockets.connect(url, **kwargs)
        logger.info("Connected to OpenAI Realtime API")

    async def session_update(
        self,
        voice: str,
        modalities: list[str] | None = None,
        turn_detection: dict[str, Any] | None = None,
    ) -> None:
        """Send session.update with voice and config."""
        modalities = modalities or ["audio", "text"]
        turn_detection = turn_detection or {
            "type": "server_vad",
            "threshold": 0.5,
            "prefix_padding_ms": 300,
            "silence_duration_ms": 500,
        }
        session = {
            "modalities": modalities,
            "voice": voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": turn_detection,
        }
        await self._send({"type": "session.update", "session": session})

    async def send_audio_frame(self, pcm16_bytes: bytes) -> None:
        """Append PCM16 audio via input_audio_buffer.append."""
        b64 = base64.b64encode(pcm16_bytes).decode("ascii")
        await self._send({"type": "input_audio_buffer.append", "audio": b64})

    async def commit_audio(self) -> None:
        """Commit input buffer via input_audio_buffer.commit."""
        await self._send({"type": "input_audio_buffer.commit"})

    async def request_response(self) -> None:
        """Trigger response generation via response.create."""
        await self._send({"type": "response.create"})

    async def cancel_response(self) -> None:
        """Cancel in-flight response (barge-in)."""
        await self._send({"type": "response.cancel"})
        await self._send({"type": "input_audio_buffer.clear"})
        logger.debug("Response cancelled")

    async def send_text(self, text: str) -> None:
        """Send user text as conversation.item.create."""
        await self._send({
            "type": "conversation.item.create",
            "item": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        })

    async def _send(self, event: dict[str, Any]) -> None:
        if self._ws is None:
            raise RuntimeError("WebSocket not connected")
        try:
            await self._ws.send(json.dumps(event))
        except Exception as e:
            from websockets.exceptions import ConnectionClosed
            if isinstance(e, ConnectionClosed):
                raise RuntimeError("WebSocket connection closed unexpectedly") from e
            raise

    async def events(self) -> AsyncIterator[dict[str, Any]]:
        """Yield server events as dicts."""
        if self._ws is None:
            return
        from websockets.exceptions import ConnectionClosed

        try:
            while True:
                msg = await self._ws.recv()
                try:
                    data = json.loads(msg)
                    yield data
                except json.JSONDecodeError as e:
                    logger.warning("Invalid JSON: %s", e)
        except ConnectionClosed:
            logger.debug("WebSocket connection closed")

    async def close(self) -> None:
        """Close WebSocket."""
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception as e:
                logger.debug("Error closing WebSocket: %s", e)
            self._ws = None
        logger.info("Realtime client closed")


def build_session_update_event(voice: str) -> dict[str, Any]:
    """Build session.update event for unit tests."""
    return {
        "type": "session.update",
        "session": {
            "modalities": ["audio", "text"],
            "voice": voice,
            "input_audio_format": "pcm16",
            "output_audio_format": "pcm16",
            "turn_detection": {"type": "server_vad", "threshold": 0.5},
        },
    }
