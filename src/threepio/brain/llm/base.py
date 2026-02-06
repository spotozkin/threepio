"""Base LLM interface."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from threepio.core.types import DialogueTurn


class BaseLLM(ABC):
    """Abstract LLM provider."""

    @abstractmethod
    def generate(
        self,
        user_input: str,
        context: list["DialogueTurn"],
    ) -> str:
        """Generate response given user input and dialogue context."""
        ...
