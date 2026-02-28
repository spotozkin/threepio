"""Text-to-speech providers."""

from threepio.speech.tts.base import BaseTTS
from threepio.speech.tts.mock_tts import MockTTS
from threepio.speech.tts.provider import get_tts_provider

__all__ = ["BaseTTS", "MockTTS", "get_tts_provider"]

# OpenAITTS imported lazily (requires optional 'openai' dep)
