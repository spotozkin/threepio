"""
Slang interpretation layer. Normalization and safety detection only; no explicit phrase lists.
Assistant silently interprets informal phrasing via prompt instruction; no semantic injection.
"""

from __future__ import annotations

import re


def _normalize_for_lookup(text: str) -> str:
    """Lowercase, collapse whitespace, strip. Expand common contractions for formal output."""
    s = " ".join((text or "").lower().split()).strip()
    s = re.sub(r"\bwhat's\b", "what is", s)
    s = re.sub(r"\bwhats\b", "what is", s)
    s = re.sub(r"\bthat's\b", "that is", s)
    s = re.sub(r"\bit's\b", "it is", s)
    s = re.sub(r"\bthere's\b", "there is", s)
    return s


def interpret_user_intent(text: str) -> str:
    """
    Normalization and safety/hazard detection only. No phrase-to-meaning replacement.
    Return safety message for possible gas-leak wording; otherwise "" (no semantic injection).
    """
    if not text or not isinstance(text, str):
        return ""
    normalized = _normalize_for_lookup(text)
    if not normalized:
        return ""

    if "gas" in normalized and ("smell" in normalized or "leak" in normalized or "odor" in normalized):
        return "The user reports a possible gas leak or gas odor and may need immediate safety guidance."

    return ""
