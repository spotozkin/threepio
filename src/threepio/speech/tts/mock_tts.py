"""Mock TTS that prints to console."""

from threepio.speech.tts.base import BaseTTS


class MockTTS(BaseTTS):
    """Mock TTS: prints [TTS] followed by the text."""

    def speak(self, text: str) -> None:
        """Print [TTS] text to stdout."""
        print(f"[TTS] {text}")
