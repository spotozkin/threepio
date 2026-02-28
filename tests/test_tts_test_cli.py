"""Tests for --tts-test CLI: help, provider validation, and synthesize contract."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Project root (parent of tests/)
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"


def test_help_includes_tts_test() -> None:
    """python -m threepio.main -h includes --tts-test."""
    env = {**os.environ, "PYTHONPATH": str(_SRC)}
    result = subprocess.run(
        [sys.executable, "-m", "threepio.main", "-h"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0
    assert "--tts-test" in result.stdout


def test_tts_test_without_valid_provider_fails_with_helpful_message() -> None:
    """Run --tts-test without PROVIDER_TTS (or with mock); assert returncode 1 and message mentions openai, elevenlabs, .envrc."""
    env = {
        **os.environ,
        "PYTHONPATH": str(_SRC),
        "AUDIO_OUTPUT_MODE": "print",
        "PROVIDER_TTS": "mock",
    }
    result = subprocess.run(
        [sys.executable, "-m", "threepio.main", "--tts-test"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env=env,
        timeout=15,
    )
    assert result.returncode == 1, (result.stdout, result.stderr)
    out = result.stdout + result.stderr
    assert "PROVIDER_TTS" in out
    assert "openai" in out or "elevenlabs" in out
    assert ".env" in out or ".envrc" in out


def test_get_tts_provider_invalid_raises_no_fallback() -> None:
    """get_tts_provider() with invalid or empty PROVIDER_TTS raises ValueError; no silent fallback to mock."""
    from threepio.speech.tts.provider import ALLOWED_PROVIDER_TTS, get_tts_provider

    from threepio.config import get_settings

    real_settings = get_settings()
    # Patch so provider_name is "invalid" (Settings Literal would reject env "invalid")
    fake_settings = patch.object(real_settings, "PROVIDER_TTS", "invalid")
    with fake_settings:
        with pytest.raises(ValueError) as exc_info:
            get_tts_provider()
        msg = str(exc_info.value)
        assert "PROVIDER_TTS" in msg
        assert "invalid" in msg
        for allowed in ALLOWED_PROVIDER_TTS:
            assert allowed in msg


def test_elevenlabs_tts_has_synthesize() -> None:
    """ElevenLabsTTS conforms to interface: has callable synthesize(text) -> bytes."""
    from threepio.speech.tts.elevenlabs_provider import ElevenLabsTTS

    assert hasattr(ElevenLabsTTS, "synthesize")
    assert callable(getattr(ElevenLabsTTS, "synthesize"))


def test_elevenlabs_synthesize_sanity_check_too_small_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """ElevenLabs synthesize() raises RuntimeError when returned audio is too small (e.g. placeholder)."""
    from threepio.speech.tts.elevenlabs_provider import ElevenLabsTTS, MIN_SYNTHESIZE_BYTES

    provider = ElevenLabsTTS(
        api_key="test-key",
        voice_id="test-voice",
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        use_streaming=False,
    )
    monkeypatch.setattr(provider, "_fetch_audio_bytes", lambda text: b"\x00\x00\x00\x00")

    with pytest.raises(RuntimeError) as exc_info:
        provider.synthesize("Hello.")
    msg = str(exc_info.value)
    assert "too little" in msg or str(MIN_SYNTHESIZE_BYTES) in msg or "128" in msg
