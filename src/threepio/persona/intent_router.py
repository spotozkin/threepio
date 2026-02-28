"""
Route user text to intent category. Heuristics only; social_slang via normal keywords only.
"""

from __future__ import annotations

import re
from typing import Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from threepio.persona.pack_schema import PersonaPack

IntentType = Literal["utility", "explanation", "urgent", "social_slang", "general"]

# Urgent: safety / emergency
_URGENT = re.compile(
    r"\b(gas|smell|fire|bleeding|choking|emergency|drowning|poison|heart attack|stroke|unconscious|call 911|call 999)\b",
    re.I,
)

# Utility: weather, time, simple factual
_UTILITY = re.compile(
    r"\b(weather|temperature|time\s*(is|now)?|what\s*(is|are)\s+(\w+)|who\s+is\s+|when\s+is\s+|where\s+is\s+|how\s+many\s+|define\s+|definition\s+of)\b",
    re.I,
)

# Explanation: teach / how does
_EXPLANATION = re.compile(
    r"\b(explain|teach|how\s+does|how\s+do\s+|why\s+does|why\s+do\s+|what\s+does\s+.+\s+mean|walk\s+me\s+through)\b",
    re.I,
)


def route_intent(
    user_text: str,
    pack_path: str | None = None,
    pack: PersonaPack | None = None,
) -> IntentType:
    """
    Classify user text into intent. Uses persona pack slang_map for social_slang detection.
    Order: urgent > utility > explanation > social_slang (slang hit) > general.
    Pass pack if already loaded to avoid reloading.
    """
    text = (user_text or "").strip()
    if not text:
        return "general"

    if _URGENT.search(text):
        return "urgent"
    if _UTILITY.search(text):
        return "utility"
    if _EXPLANATION.search(text):
        return "explanation"

    # Social: normal keywords only (no slang terms in repo)
    if re.search(r"\b(dating|relationship|courtship|partner|boyfriend|girlfriend)\b", text, re.I):
        return "social_slang"

    return "general"
