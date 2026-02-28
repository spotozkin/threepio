"""
Slang interpretation: normalize user text and return semantic labels.
Do NOT mirror slang in assistant output; enforced via prompt and optional post-guard.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from threepio.persona.pack_schema import PersonaPack


def interpret_slang(text: str, pack: PersonaPack) -> tuple[str, list[str]]:
    """
    Returns (normalized_text, labels).
    normalized_text: can be the original text; we optionally append semantic hints.
    labels: e.g. ["courtship_partner", "informal_approval"] from pack.slang_map entry "label".
    Does not modify or store verbatim dialogue; only derived labels and structure.
    """
    if not text or not pack.slang_map:
        return (text or "", [])
    text_lower = text.lower()
    words = re.findall(r"\b\w+\b", text_lower)
    labels: list[str] = []
    seen: set[str] = set()
    for w in words:
        if w in seen:
            continue
        entry = pack.slang_map.get(w)
        if isinstance(entry, dict) and "label" in entry:
            label = entry["label"]
            if label and label not in labels:
                labels.append(label)
            seen.add(w)
    # Normalized text: keep original; model will interpret. Optionally we could
    # inject a short "[user used informal terms]" hint, but keeping it minimal.
    return (text, labels)
