"""User profile persistence: preferred address, name, cooldown for ambient mode. First-run profile in .threepio/profile.json."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict

PROFILES_FILENAME = "profiles.json"
MEMORY_DIR = "data/memory"

# Project-local first-run profile (gitignored)
PROFILE_DIR = ".threepio"
PROFILE_FILENAME = "profile.json"


AddressStyle = Literal["master", "sir", "maam", "neutral", "none", "custom"]


class UserProfile(BaseModel):
    """Profile for one speaker: name, preferred address, addressing cooldown; optional first-run fields."""

    model_config = ConfigDict(validate_assignment=True)

    speaker_id: str = "default"
    name: str | None = None
    preferred_address: str | None = None
    times_seen: int = 0
    last_addressed_at: float | None = None
    # First-run profile fields (stored in .threepio/profile.json)
    display_name: Optional[str] = None
    address_style: Optional[str] = None  # master | sir | maam | neutral | none | custom
    custom_address: Optional[str] = None
    pronouns: Optional[str] = None


def get_profile_path(base_dir: str | Path = ".") -> Path:
    """Resolve path to project-local profile file. Prefer .threepio/profile.json."""
    return Path(base_dir).resolve() / PROFILE_DIR / PROFILE_FILENAME


def _profiles_path(base_dir: str | Path) -> Path:
    base = Path(base_dir)
    path = base / MEMORY_DIR / PROFILES_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_profile_file(base_dir: str | Path = ".") -> UserProfile | None:
    """Load profile from .threepio/profile.json. Returns None if file missing or invalid."""
    path = get_profile_path(base_dir)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return UserProfile.model_validate({**data, "speaker_id": data.get("speaker_id", "default")})
    except (json.JSONDecodeError, Exception):
        return None


def save_profile_file(profile: UserProfile, base_dir: str | Path = ".") -> None:
    """Persist profile to .threepio/profile.json (first-run profile)."""
    path = get_profile_path(base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.model_dump(), indent=2))


def is_interactive() -> bool:
    """True if stdin is a TTY (interactive prompt possible)."""
    return sys.stdin.isatty()


def prompt_profile() -> UserProfile:
    """Interactively prompt for display_name, address_style (menu 1-6), custom_address if needed, pronouns. Returns new UserProfile."""
    print("First-run setup: user profile (optional). Press Enter to skip a field.", flush=True)
    display_name = input("Display name (e.g. Sam): ").strip() or None
    print("Address style: 1=master 2=sir 3=ma'am 4=neutral 5=none 6=custom", flush=True)
    raw = input("Choice [4]: ").strip() or "4"
    choice_map = {"1": "master", "2": "sir", "3": "maam", "4": "neutral", "5": "none", "6": "custom"}
    address_style = choice_map.get(raw, "neutral")
    custom_address = None
    if address_style == "custom":
        custom_address = input("Custom address (e.g. Captain): ").strip() or None
    pronouns = input("Pronouns (e.g. he/him, they/them; leave blank to avoid gendered refs): ").strip() or None
    profile = UserProfile(
        speaker_id="default",
        name=display_name,
        display_name=display_name,
        address_style=address_style,
        custom_address=custom_address,
        pronouns=pronouns,
    )
    return profile


def load_or_prompt_profile(base_dir: str | Path = ".") -> UserProfile:
    """Load profile from .threepio/profile.json. If missing and interactive TTY, prompt once, save, return. Else return default profile."""
    loaded = load_profile_file(base_dir)
    if loaded is not None:
        return loaded
    if is_interactive():
        profile = prompt_profile()
        save_profile_file(profile, base_dir)
        return profile
    return UserProfile(speaker_id="default", display_name="User", address_style="neutral", pronouns=None)


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
    """Return preferred address from profile: address_style/custom_address/display_name, or legacy preferred_address/name."""
    if profile is None:
        return None
    if profile.preferred_address and profile.preferred_address.strip():
        return profile.preferred_address.strip()
    style = (profile.address_style or "neutral").lower()
    if style == "none":
        return None
    if style == "custom" and profile.custom_address:
        return profile.custom_address.strip()
    name = (profile.display_name or profile.name or "").strip()
    if style == "master":
        return f"Master {name}" if name else "Master"
    if style == "sir":
        return "sir"
    if style == "maam":
        return "ma'am"
    if style == "neutral":
        if name and name.lower() == "sam":
            return "Master Sam"  # legacy
        if name:
            return name
    if profile.name and profile.name.strip().lower() == "sam":
        return "Master Sam"
    if profile.name and profile.name.strip():
        return profile.name.strip()
    return None


def get_pronouns(profile: UserProfile | None) -> str | None:
    """Return user's pronouns if set; None means avoid gendered references."""
    if profile is None:
        return None
    return (profile.pronouns or "").strip() or None


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
