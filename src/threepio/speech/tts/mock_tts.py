"""Mock TTS that prints to console. Cannot synthesize to bytes."""

from threepio.speech.tts.base import BaseTTS


class MockTTS(BaseTTS):
    """Mock TTS: prints [TTS] followed by the text. synthesize() raises."""

    def synthesize(self, text: str) -> bytes:
        """Mock cannot produce audio bytes."""
        raise RuntimeError(
            "Mock TTS cannot synthesize to bytes. Use PROVIDER_TTS=openai or elevenlabs for --tts-test."
        )

    def speak(self, text: str) -> None:
        """Print [TTS] text to stdout."""
        print(f"[TTS] {text}")
