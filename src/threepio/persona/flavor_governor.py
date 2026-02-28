"""Flavor intent and flavor governor: intent-based response shaping."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

# Intent type aligned with intent_router (string literal for minimal coupling)
IntentType = str  # "utility" | "explanation" | "urgent" | "social_slang" | "general"


class FlavorIntent(Enum):
    CHITCHAT = "chitchat"
    TASK = "task"
    TECH_HELP = "tech_help"
    EMOTIONAL = "emotional"


# Keywords (case-insensitive) per intent
_CHITCHAT = re.compile(
    r"\b(hi|hello|hey|howdy|what'?s up|how are you|good morning|good night|thanks|thank you|bye|goodbye)\b",
    re.I,
)
_TECH_HELP = re.compile(
    r"\b(code|debug|error|install|config|api|python|script|program|fix|bug)\b",
    re.I,
)
_EMOTIONAL = re.compile(
    r"\b(sad|angry|happy|frustrated|worried|anxious|calm|feel|feeling|sorry|miss)\b",
    re.I,
)


def flavor_intent(user_text: str) -> FlavorIntent:
    """Classify user text with simple keyword rules. Default TASK."""
    text = (user_text or "").strip()
    if _CHITCHAT.search(text):
        return FlavorIntent.CHITCHAT
    if _TECH_HELP.search(text):
        return FlavorIntent.TECH_HELP
    if _EMOTIONAL.search(text):
        return FlavorIntent.EMOTIONAL
    return FlavorIntent.TASK


def decide_flavor(intent: str, mode: str) -> dict[str, Any]:
    """
    Given intent (from intent_router) and mode, return flavor dict for prompt:
    max_asides, anxiety_level, format, exclamations.
    Used to guide prompt content (flavor block).
    """
    # Urgent: no asides, low anxiety but serious, steps format, exclamations rare
    if intent == "urgent":
        return {
            "max_asides": 0,
            "anxiety_level": "low",
            "format": "steps",
            "exclamations": "rare",
        }
    # Utility: no asides, no anxiety, direct, no exclamations
    if intent == "utility":
        return {
            "max_asides": 0,
            "anxiety_level": "none",
            "format": "direct",
            "exclamations": "rare",
        }
    # Explanation: 0-1 aside, low anxiety, bullets
    if intent == "explanation":
        return {
            "max_asides": 1,
            "anxiety_level": "low",
            "format": "bullets",
            "exclamations": "rare",
        }
    # Social/slang: interpret then formal; 0-1 aside
    if intent == "social_slang":
        return {
            "max_asides": 1,
            "anxiety_level": "low",
            "format": "direct",
            "exclamations": "rare",
        }
    # General
    return {
        "max_asides": 1,
        "anxiety_level": "low",
        "format": "direct",
        "exclamations": "rare",
    }
