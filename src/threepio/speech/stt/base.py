"""Base STT interface."""

from abc import ABC, abstractmethod


class BaseSTT(ABC):
    """Abstract speech-to-text provider."""

    @abstractmethod
    def listen(self) -> str:
        """Listen and return transcribed text."""
        ...
