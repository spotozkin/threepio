"""
Persona pack schema. No pydantic; validate_pack checks required keys and types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PersonaPack:
    """Runtime persona pack loaded from JSON (offline-built)."""

    id: str
    voice: dict[str, Any]
    behavior: dict[str, Any]
    style_rules: list[str]
    allowed_asides: list[str]
    phrase_fragments: dict[str, list[str]]
    response_shapes: dict[str, str]
    slang_map: dict[str, dict[str, str]]
    speech_profile: dict[str, Any]


_REQUIRED_TOP_KEYS = (
    "id",
    "voice",
    "behavior",
    "style_rules",
    "allowed_asides",
    "phrase_fragments",
    "response_shapes",
    "slang_map",
    "speech_profile",
)


def validate_pack(data: dict[str, Any]) -> PersonaPack:
    """
    Validate dict has required keys and types. Raises ValueError on failure.
    No pydantic dependency.
    """
    if not isinstance(data, dict):
        raise ValueError("Persona pack must be a dict")
    for key in _REQUIRED_TOP_KEYS:
        if key not in data:
            raise ValueError(f"Persona pack missing required key: {key}")
    id_val = data["id"]
    if not isinstance(id_val, str):
        raise ValueError("pack.id must be str")
    for key in ("voice", "behavior", "phrase_fragments", "response_shapes", "slang_map", "speech_profile"):
        if not isinstance(data[key], dict):
            raise ValueError(f"pack.{key} must be dict")
    if not isinstance(data["style_rules"], list):
        raise ValueError("pack.style_rules must be list")
    if not isinstance(data["allowed_asides"], list):
        raise ValueError("pack.allowed_asides must be list")
    for item in data["allowed_asides"]:
        if not isinstance(item, str):
            raise ValueError("pack.allowed_asides must be list of str")
    for k, v in data["phrase_fragments"].items():
        if not isinstance(v, list):
            raise ValueError(f"pack.phrase_fragments[{k!r}] must be list")
        for s in v:
            if not isinstance(s, str):
                raise ValueError(f"pack.phrase_fragments[{k!r}] must be list of str")
    for k, v in data["slang_map"].items():
        if not isinstance(v, dict):
            raise ValueError(f"pack.slang_map[{k!r}] must be dict")
        if "meaning" not in v or not isinstance(v.get("meaning"), str):
            raise ValueError(f"pack.slang_map[{k!r}] must contain 'meaning' as str")
        if "label" in v and not isinstance(v["label"], str):
            raise ValueError(f"pack.slang_map[{k!r}].label must be str if present")
    return PersonaPack(
        id=data["id"],
        voice=dict(data["voice"]),
        behavior=dict(data["behavior"]),
        style_rules=list(data["style_rules"]),
        allowed_asides=list(data["allowed_asides"]),
        phrase_fragments={k: list(v) for k, v in data["phrase_fragments"].items()},
        response_shapes=dict(data["response_shapes"]),
        slang_map={k: dict(v) for k, v in data["slang_map"].items()},
        speech_profile=dict(data["speech_profile"]),
    )
