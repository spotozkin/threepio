"""ElevenLabs TTS: playback uses AUDIO_OUTPUT_MODE and speech.playback (no 'No speaker configured')."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_elevenlabs_speak_uses_playback_with_afplay_mode() -> None:
    """With AUDIO_OUTPUT_MODE=afplay, speak() uses shared playback and does not raise 'No speaker configured'."""
    from threepio.speech.tts.elevenlabs_provider import ElevenLabsTTS

    mock_handle = MagicMock()
    mock_handle.is_running.return_value = False  # playback "finished" immediately so loop exits
    mock_handle.stop.return_value = None

    mock_settings = MagicMock()
    mock_settings.AUDIO_OUTPUT_MODE = "afplay"

    with patch("threepio.config.get_settings", return_value=mock_settings):
        with patch(
            "threepio.speech.playback.play_audio_file_interruptible",
            return_value=mock_handle,
        ) as m_play:
            tts = ElevenLabsTTS(
                api_key="test-key",
                voice_id="test-voice",
                output_format="mp3_44100_128",
                speaker=None,
            )
            # synthesize_to_file will be called; mock it to write a minimal file so path exists
            with patch.object(tts, "synthesize_to_file", side_effect=lambda text, path: Path(path).write_bytes(b"\x00" * 44)):
                tts.speak("hello")
    # Should have used shared playback (no "No speaker configured" raised)
    m_play.assert_called_once()


def test_elevenlabs_speak_print_mode_skips_playback() -> None:
    """With AUDIO_OUTPUT_MODE=print, speak() does not call playback."""
    from threepio.speech.tts.elevenlabs_provider import ElevenLabsTTS

    mock_settings = MagicMock()
    mock_settings.AUDIO_OUTPUT_MODE = "print"

    with patch("threepio.config.get_settings", return_value=mock_settings):
        with patch("threepio.speech.playback.play_audio_file_interruptible") as m_play:
            tts = ElevenLabsTTS(
                api_key="test-key",
                voice_id="test-voice",
                output_format="mp3_44100_128",
                speaker=None,
            )
            with patch.object(tts, "synthesize_to_file", side_effect=lambda text, path: Path(path).write_bytes(b"\x00" * 44)):
                tts.speak("hi")
    m_play.assert_not_called()
