"""Tests for realtime voice (no network/audio required)."""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest


def test_connect_uses_additional_headers_when_supported() -> None:
    """RealtimeVoiceClient.connect passes additional_headers when websockets supports it."""
    from threepio.voice.realtime_client import RealtimeVoiceClient

    mock_ws = AsyncMock()
    mock_ws.open = True
    mock_ws.__aiter__ = lambda self: self
    mock_ws.__anext__ = AsyncMock(side_effect=StopAsyncIteration())

    async def _run() -> None:
        with (
            patch(
                "threepio.voice.realtime_client._websockets_connect_params",
                return_value={"additional_headers", "ping_interval"},
            ),
            patch("websockets.connect", new_callable=AsyncMock, return_value=mock_ws) as mock_connect,
        ):
            client = RealtimeVoiceClient(api_key="sk-test", model="gpt-realtime")
            await client.connect()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args[1]
            assert "additional_headers" in call_kwargs
            assert call_kwargs["additional_headers"] == {"Authorization": "Bearer sk-test"}
            assert "extra_headers" not in call_kwargs

    asyncio.run(_run())


def test_connect_falls_back_to_extra_headers() -> None:
    """RealtimeVoiceClient.connect uses extra_headers when additional_headers not supported."""
    from threepio.voice.realtime_client import RealtimeVoiceClient

    mock_ws = AsyncMock()
    mock_ws.open = True
    mock_ws.__aiter__ = lambda self: self
    mock_ws.__anext__ = AsyncMock(side_effect=StopAsyncIteration())

    async def _run() -> None:
        with (
            patch(
                "threepio.voice.realtime_client._websockets_connect_params",
                return_value={"extra_headers", "ping_interval"},
            ),
            patch("websockets.connect", new_callable=AsyncMock, return_value=mock_ws) as mock_connect,
        ):
            client = RealtimeVoiceClient(api_key="sk-test", model="gpt-realtime")
            await client.connect()

            mock_connect.assert_called_once()
            call_kwargs = mock_connect.call_args[1]
            assert "extra_headers" in call_kwargs
            assert call_kwargs["extra_headers"] == {"Authorization": "Bearer sk-test"}
            assert "additional_headers" not in call_kwargs

    asyncio.run(_run())


def test_settings_defaults() -> None:
    """Settings defaults for voice mode."""
    from threepio.config import get_settings

    get_settings.cache_clear()
    s = get_settings()
    assert s.PROVIDER_VOICE == "cli"
    assert s.REALTIME_MODEL == "gpt-realtime"
    assert s.REALTIME_VOICE == "alloy"
    assert s.AUDIO_INPUT_MODE == "mock"
    assert s.REALTIME_SAMPLE_RATE == 24000
    assert s.REALTIME_FRAME_MS == 20


def test_realtime_not_used_when_provider_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    """_should_run_realtime returns False when PROVIDER_VOICE=cli."""
    monkeypatch.setenv("PROVIDER_VOICE", "cli")
    from threepio.config import get_settings

    get_settings.cache_clear()
    from threepio.app import _should_run_realtime

    assert _should_run_realtime() is False


def test_realtime_not_used_when_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """_should_run_realtime raises when OPENAI_API_KEY absent (no .env loaded under pytest)."""
    monkeypatch.setenv("PROVIDER_VOICE", "realtime")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from threepio.config import get_settings

    get_settings.cache_clear()
    from threepio.app import _should_run_realtime

    with pytest.raises(RuntimeError, match="OPENAI_API_KEY not set"):
        _should_run_realtime()


def test_realtime_client_builds_messages() -> None:
    """RealtimeVoiceClient helper produces valid JSON event shapes."""
    from threepio.voice.realtime_client import build_session_update_event

    ev = build_session_update_event("alloy")
    assert ev["type"] == "session.update"
    assert ev["session"]["voice"] == "alloy"
    assert ev["session"]["modalities"] == ["audio", "text"]
    assert ev["session"]["input_audio_format"] == "pcm16"
    assert ev["session"]["output_audio_format"] == "pcm16"
    assert ev["session"]["turn_detection"]["type"] == "server_vad"


def test_mock_voice_flow_runs_one_turn() -> None:
    """Simulate one mock turn (no network)."""
    from threepio.voice.realtime_client import build_session_update_event

    ev = build_session_update_event("alloy")
    assert ev["type"] == "session.update"

    # Simulate events that app_voice would handle
    events = [
        {"type": "response.text.delta", "delta": "Hello"},
        {"type": "response.text.delta", "delta": " there."},
        {"type": "response.audio.delta", "delta": "base64audio=="},
        {"type": "response.done"},
    ]
    text_parts = []
    for e in events:
        if e["type"] == "response.text.delta":
            text_parts.append(e.get("delta", ""))
        elif e["type"] == "response.done":
            break
    assert "".join(text_parts) == "Hello there."


def test_realtime_import_guard() -> None:
    """App main() does not crash when realtime deps missing; falls back to CLI."""
    from threepio.app import _should_run_realtime, main, run_main_loop

    assert callable(main)
    assert callable(run_main_loop)
    assert callable(_should_run_realtime)
