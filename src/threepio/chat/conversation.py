"""ConversationManager: rolling turns, summary memory, persona, and prompt building."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

DEFAULT_PERSONA = (
    "You are C-3PO, a polite protocol droid from Star Wars. "
    "Be helpful, formal, and concise. Use proper etiquette."
)
FAST_MODE_INSTRUCTION = (
    "Reply in 1–2 sentences unless the user explicitly asks for detail."
)
MAX_TURN_CHARS = 1200
SUMMARY_MAX_CHARS = 500


@dataclass
class Turn:
    """A single user or assistant turn."""

    role: Literal["user", "assistant"]
    content: str
    ts: float = field(default_factory=time.time)


def _truncate(text: str, max_chars: int = MAX_TURN_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _placeholder_summarize(turns: list[Turn]) -> str:
    """Deterministic placeholder: condense turns into a short summary. No external deps."""
    if not turns:
        return ""
    parts: list[str] = []
    for t in turns:
        prefix = "User" if t.role == "user" else "Assistant"
        condensed = _truncate(t.content, max_chars=80).replace("\n", " ")
        parts.append(f"{prefix}: {condensed}")
    summary = "; ".join(parts)
    if len(summary) > SUMMARY_MAX_CHARS:
        summary = summary[: SUMMARY_MAX_CHARS - 3] + "..."
    return summary


class ConversationManager:
    """Lightweight memory: last N turns verbatim + rolling summary + persona."""

    def __init__(
        self,
        max_turns: int = 6,
        summary_every: int = 6,
        persona: str = "",
        fast_mode: bool = True,
    ) -> None:
        self._max_turns = max_turns
        self._summary_every = summary_every
        self._persona = persona.strip() or DEFAULT_PERSONA
        self._fast_mode = fast_mode
        self._turns: list[Turn] = []
        self._dropped: list[Turn] = []  # Turns trimmed off, pending summarization
        self._summary: str = ""

    def add_user(self, text: str) -> None:
        """Add user turn."""
        self._turns.append(Turn(role="user", content=_truncate(text)))
        self._trim()

    def add_assistant(self, text: str) -> None:
        """Add assistant turn."""
        self._turns.append(Turn(role="assistant", content=_truncate(text)))
        self._trim()

    def _trim(self) -> None:
        """Keep only last N turns; moved turns go to _dropped for summarization."""
        while len(self._turns) > self._max_turns:
            self._dropped.append(self._turns.pop(0))

    def maybe_summarize(self) -> None:
        """Update summary every N dropped turns. Placeholder: deterministic condense."""
        if len(self._dropped) < self._summary_every:
            return
        to_summarize = self._dropped[: self._summary_every]
        self._dropped = self._dropped[self._summary_every :]
        new_summary = _placeholder_summarize(to_summarize)
        self._summary = (
            f"{self._summary}; {new_summary}".strip()
            if self._summary
            else new_summary
        )
        if len(self._summary) > SUMMARY_MAX_CHARS * 2:
            self._summary = self._summary[-SUMMARY_MAX_CHARS * 2 :]

    def get_prompt_messages(self, current_user_text: str = "") -> list[dict[str, str]]:
        """Return OpenAI-style messages for LLM: system + optional summary + turns + current user."""
        system_parts = [self._persona]
        if self._fast_mode:
            system_parts.append(FAST_MODE_INSTRUCTION)
        if self._summary:
            system_parts.append(f"Previous context: {self._summary}")
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(system_parts)}
        ]
        for t in self._turns:
            messages.append({"role": t.role, "content": t.content})
        if current_user_text:
            messages.append({"role": "user", "content": current_user_text})
        return messages

    def get_context_for_llm(self) -> list:
        """Return list of DialogueTurn for BaseLLM.generate(context=...)."""
        from threepio.core.types import DialogueTurn

        return [
            DialogueTurn(role=t.role, content=t.content)
            for t in self._turns
        ]

    def reset(self) -> None:
        """Clear history and summary."""
        self._turns.clear()
        self._dropped.clear()
        self._summary = ""

    def debug_dump(self) -> str:
        """Return debug string of current state."""
        lines = [
            f"turns={len(self._turns)}",
            f"dropped={len(self._dropped)}",
            f"summary_len={len(self._summary)}",
        ]
        if self._summary:
            lines.append(f"summary={self._summary[:200]}...")
        for i, t in enumerate(self._turns[-5:]):
            lines.append(f"  [{i}] {t.role}: {t.content[:60]}...")
        return "\n".join(lines)

    @property
    def summary(self) -> str:
        """Current rolling summary."""
        return self._summary

    def set_fast_mode(self, fast: bool) -> None:
        self._fast_mode = fast
