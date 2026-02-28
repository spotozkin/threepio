"""Tests for threepio.persona.prompt_builder."""

import pytest

from threepio.memory.user_profile import UserProfile
from threepio.persona.prompt_builder import DEFAULT_PROMPT, build_c3po_system_prompt


def test_prompt_contains_c3po() -> None:
    """Prompt contains C-3PO and is non-empty."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "C-3PO" in out
    assert len(out) > 0


def test_prompt_includes_master_sam_when_profile_says_so() -> None:
    """When profile has name Sam or preferred_address Master Sam, prompt includes it."""
    p = UserProfile(speaker_id="x", name="Sam")
    out = build_c3po_system_prompt(p, mode="ambient")
    assert "Master Sam" in out
    p2 = UserProfile(speaker_id="x", preferred_address="Master Sam")
    out2 = build_c3po_system_prompt(p2, mode="ambient")
    assert "Master Sam" in out2


def test_default_prompt_constant() -> None:
    """DEFAULT_PROMPT is defined and contains THREEPIO."""
    assert "THREEPIO" in DEFAULT_PROMPT
