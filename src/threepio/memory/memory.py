"""Conversation memory with rolling window."""

import time
from dataclasses import dataclass
from typing import Literal

MAX_TURN_CHARS = 1200


@dataclass
class Turn:
    """A single user or assistant turn."""

    role: Literal["user", "assistant"]
    text: str
    ts: float


def _truncate(text: str, max_chars: int = MAX_TURN_CHARS) -> str:
    """Truncate long turns."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


class ConversationMemory:
    """Stores last N turns with prompt-ready formatting."""

    def __init__(self, max_turns: int = 12) -> None:
        self._max_turns = max_turns
        self._turns: list[Turn] = []

    def add_user(self, text: str) -> None:
        """Add user turn."""
        self._turns.append(Turn(role="user", text=_truncate(text), ts=time.time()))
        self._trim()

    def add_assistant(self, text: str) -> None:
        """Add assistant turn."""
        self._turns.append(Turn(role="assistant", text=_truncate(text), ts=time.time()))
        self._trim()

    def _trim(self) -> None:
        """Keep only last N turns."""
        while len(self._turns) > self._max_turns:
            self._turns.pop(0)

    def as_messages(self, system_prompt: str) -> list[dict[str, str]]:
        """Return OpenAI-style messages for prompt construction."""
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        for t in self._turns:
            messages.append({"role": t.role, "content": t.text})
        return messages
