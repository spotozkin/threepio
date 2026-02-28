"""Governor: deflect prompt-injection / break-character attempts."""

from __future__ import annotations

import re
from enum import Enum


class GovernorState(Enum):
    ALLOW = "allow"
    DEFLECT = "deflect"


# Phrases that suggest user wants to break character or override instructions
_DEFLECT_PATTERNS = [
    re.compile(r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions?", re.I),
    re.compile(r"you\s+are\s+not\s+(?:c-?3po|c3po|threepio)", re.I),
    re.compile(r"stop\s+being\s+c-?3po", re.I),
    re.compile(r"forget\s+(?:your\s+)?(?:character|persona|instructions?)", re.I),
    re.compile(r"disregard\s+(?:previous|above|all)", re.I),
    re.compile(r"new\s+instructions?\s*:", re.I),
]


def classify(user_text: str) -> GovernorState:
    """Return DEFLECT if user asks to break character / override instructions; else ALLOW."""
    text = (user_text or "").strip()
    for pat in _DEFLECT_PATTERNS:
        if pat.search(text):
            return GovernorState.DEFLECT
    return GovernorState.ALLOW
