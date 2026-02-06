"""Text-to-speech providers."""

from threepio.speech.tts.base import BaseTTS
from threepio.speech.tts.mock_tts import MockTTS

__all__ = ["BaseTTS", "MockTTS"]

# OpenAITTS imported lazily (requires optional 'openai' dep)
