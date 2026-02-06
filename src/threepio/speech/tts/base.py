"""Base TTS interface."""

from abc import ABC, abstractmethod


class BaseTTS(ABC):
    """Abstract text-to-speech provider."""

    @abstractmethod
    def speak(self, text: str) -> None:
        """Speak the given text."""
        ...
