"""Tests for threepio.memory.user_profile."""

import json
from pathlib import Path

import pytest

from threepio.memory.user_profile import (
    UserProfile,
    get_preferred_address,
    load_profile,
    mark_addressed,
    save_profile,
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
