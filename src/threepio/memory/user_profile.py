"""User profile persistence: preferred address, name, cooldown for ambient mode."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

PROFILES_FILENAME = "profiles.json"
MEMORY_DIR = "data/memory"


class UserProfile(BaseModel):
    """Profile for one speaker: name, preferred address, and addressing cooldown."""

    model_config = ConfigDict(validate_assignment=True)

    speaker_id: str
    name: str | None = None
    preferred_address: str | None = None
    times_seen: int = 0
    last_addressed_at: float | None = None


def _profiles_path(base_dir: str | Path) -> Path:
    base = Path(base_dir)
    path = base / MEMORY_DIR / PROFILES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_profile(speaker_id: str, base_dir: str | Path = ".") -> UserProfile:
    """Load profile for speaker_id from JSON; create default if missing."""
    path = _profiles_path(base_dir)
    if not path.exists():
        return UserProfile(speaker_id=speaker_id)
    import json
    data = json.loads(path.read_text())
    if speaker_id not in data:
        return UserProfile(speaker_id=speaker_id)
    return UserProfile.model_validate(data[speaker_id])


def save_profile(profile: UserProfile, base_dir: str | Path = ".") -> None:
    """Persist profile to JSON (merge with existing by speaker_id)."""
    path = _profiles_path(base_dir)
    import json
    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {}
    data[profile.speaker_id] = profile.model_dump()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


# Patterns for update_from_user_text
_CALL_ME = re.compile(r"(?:call\s+me|my\s+name\s+is|i(?:'m|\s+am)\s+)\s*([^.?!]+)", re.I)
_ADDRESS_AS = re.compile(r"address\s+me\s+as\s+([^.?!]+)", re.I)


def update_from_user_text(profile: UserProfile, text: str) -> UserProfile:
    """Update name/preferred_address from phrases like 'call me X', 'address me as Y'. Returns updated profile."""
    text = (text or "").strip()
    if not text:
        return profile
    m = _CALL_ME.search(text)
    if m:
        raw = m.group(1).strip()
        name = raw.split(",")[0].strip() if raw else ""
        if name:
            profile = profile.model_copy(update={"name": name})
    m = _ADDRESS_AS.search(text)
    if m:
        addr = m.group(1).strip()
        if addr:
            profile = profile.model_copy(update={"preferred_address": addr})
    return profile


def get_preferred_address(profile: UserProfile | None) -> str | None:
    """Return preferred address: preferred_address, or 'Master Sam' if name is Sam, else name."""
    if profile is None:
        return None
    if profile.preferred_address:
        return profile.preferred_address.strip() or None
    if profile.name and profile.name.strip().lower() == "sam":
        return "Master Sam"
    if profile.name and profile.name.strip():
        return profile.name.strip()
    return None


def should_inject_address(
    profile: UserProfile | None,
    now: float,
    cooldown_s: float = 90.0,
) -> bool:
    """True if we should inject address this turn (never addressed or cooldown elapsed)."""
    if profile is None:
        return False
    if profile.last_addressed_at is None:
        return True
    return (now - profile.last_addressed_at) >= cooldown_s


def mark_addressed(profile: UserProfile, now: float) -> None:
    """Set last_addressed_at to now (mutates profile)."""
    profile.last_addressed_at = now
