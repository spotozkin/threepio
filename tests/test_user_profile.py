"""Tests for threepio.memory.user_profile."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from threepio.memory.user_profile import (
    UserProfile,
    get_preferred_address,
    get_profile_path,
    get_pronouns,
    load_or_prompt_profile,
    load_profile,
    load_profile_file,
    mark_addressed,
    save_profile,
    save_profile_file,
    should_inject_address,
    update_from_user_text,
)


def test_load_save_roundtrip(tmp_path: Path) -> None:
    """load_profile and save_profile roundtrip."""
    p = UserProfile(speaker_id="test", name="Sam", preferred_address="Master Sam")
    save_profile(p, tmp_path)
    path = tmp_path / "data" / "memory" / "profiles.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["test"]["speaker_id"] == "test"
    assert data["test"]["name"] == "Sam"
    loaded = load_profile("test", tmp_path)
    assert loaded.speaker_id == p.speaker_id
    assert loaded.name == p.name
    assert loaded.preferred_address == p.preferred_address


def test_update_from_user_text_sets_name_and_address() -> None:
    """update_from_user_text sets name and preferred_address from phrases."""
    p = UserProfile(speaker_id="x")
    p2 = update_from_user_text(p, "By the way, call me Alice.")
    assert p2.name == "Alice"
    p3 = update_from_user_text(p2, "Address me as Your Highness.")
    assert p3.preferred_address == "Your Highness"
    p4 = update_from_user_text(p3, "My name is Bob.")
    assert p4.name == "Bob"


def test_get_preferred_address_master_sam() -> None:
    """get_preferred_address returns 'Master Sam' when name is Sam."""
    p = UserProfile(speaker_id="x", name="Sam")
    assert get_preferred_address(p) == "Master Sam"
    p2 = UserProfile(speaker_id="x", name="sam")
    assert get_preferred_address(p2) == "Master Sam"
    p3 = UserProfile(speaker_id="x", preferred_address="Sir")
    assert get_preferred_address(p3) == "Sir"
    p4 = UserProfile(speaker_id="x", name="Alice")
    assert get_preferred_address(p4) == "Alice"
    assert get_preferred_address(None) is None


def test_should_inject_address_and_mark_addressed_cooldown() -> None:
    """should_inject_address and mark_addressed respect cooldown."""
    p = UserProfile(speaker_id="x")
    t0 = 1000.0
    assert should_inject_address(p, t0, cooldown_s=90.0) is True
    mark_addressed(p, t0)
    assert p.last_addressed_at == t0
    assert should_inject_address(p, t0 + 50.0, cooldown_s=90.0) is False
    assert should_inject_address(p, t0 + 91.0, cooldown_s=90.0) is True


def test_get_profile_path() -> None:
    """get_profile_path returns .threepio/profile.json under base_dir."""
    p = get_profile_path(".")
    assert p.name == "profile.json"
    assert p.parent.name == ".threepio"
    assert get_profile_path(Path("/foo")).as_posix().endswith(".threepio/profile.json")


def test_load_save_profile_file_roundtrip(tmp_path: Path) -> None:
    """load_profile_file and save_profile_file roundtrip for .threepio/profile.json."""
    profile = UserProfile(
        speaker_id="default",
        display_name="Sam",
        address_style="master",
        custom_address=None,
        pronouns="he/him",
    )
    save_profile_file(profile, tmp_path)
    path = tmp_path / ".threepio" / "profile.json"
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["display_name"] == "Sam"
    assert data["address_style"] == "master"
    assert data["pronouns"] == "he/him"
    loaded = load_profile_file(tmp_path)
    assert loaded is not None
    assert loaded.display_name == profile.display_name
    assert loaded.address_style == profile.address_style
    assert loaded.pronouns == profile.pronouns


def test_load_profile_file_missing_returns_none(tmp_path: Path) -> None:
    """load_profile_file returns None when .threepio/profile.json is missing."""
    assert load_profile_file(tmp_path) is None


def test_load_or_prompt_profile_non_interactive_returns_default(tmp_path: Path) -> None:
    """When not a TTY, load_or_prompt_profile returns default profile without prompting."""
    with patch("sys.stdin.isatty", return_value=False):
        p = load_or_prompt_profile(tmp_path)
    assert p.speaker_id == "default"
    assert p.display_name is None
    assert p.address_style == "neutral"


def test_load_or_prompt_profile_loads_existing(tmp_path: Path) -> None:
    """When .threepio/profile.json exists, load_or_prompt_profile loads it."""
    save_profile_file(
        UserProfile(speaker_id="default", display_name="Jay", address_style="sir", pronouns="they/them"),
        tmp_path,
    )
    with patch("sys.stdin.isatty", return_value=False):
        p = load_or_prompt_profile(tmp_path)
    assert p.display_name == "Jay"
    assert p.address_style == "sir"
    assert p.pronouns == "they/them"


def test_get_preferred_address_by_style() -> None:
    """get_preferred_address respects address_style and custom_address."""
    assert get_preferred_address(UserProfile(speaker_id="x", address_style="none")) is None
    assert get_preferred_address(UserProfile(speaker_id="x", address_style="custom", custom_address="Captain")) == "Captain"
    assert get_preferred_address(UserProfile(speaker_id="x", display_name="Sam", address_style="master")) == "Master Sam"
    assert get_preferred_address(UserProfile(speaker_id="x", address_style="sir")) == "sir"
    assert get_preferred_address(UserProfile(speaker_id="x", address_style="maam")) == "ma'am"
    assert get_preferred_address(UserProfile(speaker_id="x", display_name="Alex", address_style="neutral")) == "Alex"


def test_get_pronouns() -> None:
    """get_pronouns returns profile.pronouns or None."""
    assert get_pronouns(None) is None
    assert get_pronouns(UserProfile(speaker_id="x")) is None
    assert get_pronouns(UserProfile(speaker_id="x", pronouns="they/them")) == "they/them"
