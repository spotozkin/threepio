"""C-3PO persona: polite, formal, slightly anxious, verbose."""

from datetime import datetime
from hashlib import sha256
from typing import Sequence

# Rotating flavor phrases (deterministic via hash of user text)
OPENING_PHRASES: Sequence[str] = (
    "Certainly!",
    "Oh my!",
    "I beg your pardon—",
    "Good heavens!",
    "As you wish.",
    "I am pleased to report that",
    "If I may be of assistance:",
)


def _pick_phrase(user_text: str, phrases: Sequence[str]) -> str:
    """Choose phrase deterministically from hash of user text."""
    h = sha256(user_text.strip().lower().encode()).hexdigest()
    idx = int(h[:8], 16) % len(phrases)
    return phrases[idx]


class ThreepioPersona:
    """Formats responses in C-3PO's voice."""

    def format_tool_response(self, tool_name: str, data: dict, user_text: str = "") -> str:
        """Format a single tool result with persona voice."""
        opening = _pick_phrase(user_text or tool_name, OPENING_PHRASES)

        if tool_name == "time":
            iso = data.get("iso", "")
            try:
                dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                tstr = dt.strftime("%I:%M %p")
            except Exception:
                tstr = iso or "unknown"
            return f"{opening} The current time is {tstr}."

        if tool_name == "stocks":
            sym = data.get("symbol", "?")
            price = data.get("price", "?")
            src = data.get("source", "")
            suffix = " (I must note, this is mock data.)" if src == "mock" else ""
            return f"{opening} The stock price of {sym} is ${price}.{suffix}"

        if tool_name == "weather":
            loc = data.get("location", "that location")
            temp = data.get("temp_f", "?")
            cond = data.get("condition", "unknown")
            return (
                f"{opening} In {loc}, it is {temp}°F and {cond}. "
                "Do take appropriate precautions for the conditions."
            )

        return f"{opening} I have retrieved the requested information."

    def format_generic_response(self, user_text: str) -> str:
        """Format response when no tools matched."""
        opening = _pick_phrase(user_text, OPENING_PHRASES)
        return (
            f"I am C-3PO, human-cyborg relations. {opening} "
            "I am afraid I do not have specific information on that particular matter. "
            "How else may I be of service to you, Sir or Madam?"
        )

    def format_error(self, message: str) -> str:
        """Format an error in persona voice."""
        return (
            "Oh dear! I do apologize. "
            "I was unable to retrieve that information. "
            f"{message or 'An unfortunate error has occurred.'} "
            "Might I suggest trying again?"
        )
