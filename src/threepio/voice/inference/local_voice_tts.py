"""Local voice TTS (placeholder – not wired into app yet)."""

from threepio.speech.tts.base import BaseTTS


class LocalVoiceTTS(BaseTTS):
    """TTS using locally trained voice model. Stub until pipeline is complete."""

    def __init__(self, model_dir: str) -> None:
        self._model_dir = model_dir

    def speak(self, text: str) -> None:
        """Speak text using local voice model."""
        raise NotImplementedError("Local voice TTS not yet implemented")
