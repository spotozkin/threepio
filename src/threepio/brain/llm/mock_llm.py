"""Mock LLM with C-3PO persona."""

from threepio.brain.llm.base import BaseLLM
from threepio.character.persona import PERSONA_RULES
from threepio.core.types import DialogueTurn


class MockLLM(BaseLLM):
    """Mock LLM: returns THREEPIO-styled responses based on persona rules."""

    def generate(
        self,
        user_input: str,
        context: list[DialogueTurn],
    ) -> str:
        """Return a C-3PO-styled mock response."""
        text = user_input.strip().lower()

        if not text:
            return "I am C-3PO, human-cyborg relations. How may I be of assistance?"

        # Apply persona rules
        for trigger, response in PERSONA_RULES:
            if trigger in text:
                return response

        # Default polite C-3PO-style response
        return (
            "Oh my! I do believe I understand. "
            "As a protocol droid, I am programmed for etiquette and translation. "
            f"Your message regarding '{user_input[:50]}' has been noted. "
            "Is there anything else?"
        )
