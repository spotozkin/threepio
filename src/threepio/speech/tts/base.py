"""Base TTS interface. All providers must implement synthesize(text) -> bytes."""

from abc import ABC, abstractmethod


class BaseTTS(ABC):
    """Abstract text-to-speech provider. Canonical interface: synthesize(text) -> bytes."""

    @abstractmethod
    def synthesize(self, text: str) -> bytes:
        """Synthesize text to raw audio bytes. Caller handles format and file writing."""
        ...

    @abstractmethod
    def speak(self, text: str) -> None:
        """Speak the given text (optional; may use speaker or print)."""
        ...
