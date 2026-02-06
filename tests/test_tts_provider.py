"""Tests for TTS and app components."""

import pytest

from threepio.speech.tts.mock_tts import MockTTS


def test_mock_tts_works_without_api_key() -> None:
    """MockTTS works without any API key or external deps."""
    tts = MockTTS()
    tts.speak("hello")
    # No crash; MockTTS just prints
