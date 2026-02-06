"""Shared types."""

from dataclasses import dataclass
from typing import Literal


@dataclass
class DialogueTurn:
    """A single user/assistant exchange."""

    role: Literal["user", "assistant"]
    content: str
