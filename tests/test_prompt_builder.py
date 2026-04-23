"""Tests for threepio.persona.prompt_builder."""

import pytest

from threepio.memory.user_profile import UserProfile
from threepio.persona.prompt_builder import (
    DEFAULT_PROMPT,
    build_c3po_system_prompt,
    star_wars_knowledge_style,
)


def test_star_wars_knowledge_style_first_person_ok() -> None:
    """Topics C-3PO plausibly witnessed -> first_person_ok."""
    assert star_wars_knowledge_style("Who is Luke?") == "first_person_ok"
    assert star_wars_knowledge_style("Tell me about Cloud City") == "first_person_ok"
    assert star_wars_knowledge_style("What happened on the Death Star?") == "first_person_ok"
    assert star_wars_knowledge_style("Han and Chewbacca") == "first_person_ok"
    assert star_wars_knowledge_style("princess leia") == "first_person_ok"


def test_star_wars_knowledge_style_indirect_only() -> None:
    """Topics C-3PO likely did not witness -> indirect_only."""
    assert star_wars_knowledge_style("What was the Clone Wars?") == "indirect_only"
    assert star_wars_knowledge_style("Tell me about Order 66") == "indirect_only"
    assert star_wars_knowledge_style("Darth Maul") == "indirect_only"
    assert star_wars_knowledge_style("Ahsoka Tano") == "indirect_only"
    assert star_wars_knowledge_style("") == "indirect_only"
    assert star_wars_knowledge_style("  ") == "indirect_only"


def test_star_wars_knowledge_style_indirect_overrides_first_person() -> None:
    """If both appear, indirect_only wins (safer)."""
    assert star_wars_knowledge_style("Luke and the Clone Wars") == "indirect_only"


def test_star_wars_mode_includes_style_rule() -> None:
    """When user_text is SW and first_person_ok, prompt allows first-person; when indirect_only, prompt forbids claiming witness."""
    out_ok = build_c3po_system_prompt(None, mode="ambient", user_text="Who is Luke?")
    assert "first-person recollection when plausible" in out_ok or "first-person" in out_ok
    out_indirect = build_c3po_system_prompt(None, mode="ambient", user_text="What was the Clone Wars?")
    assert "Do NOT claim you personally witnessed" in out_indirect


def test_prompt_contains_c3po() -> None:
    """Prompt contains C-3PO and is non-empty."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "C-3PO" in out
    assert len(out) > 0


def test_prompt_includes_master_sam_when_profile_says_so() -> None:
    """When profile has address_style=master and display_name Sam, or preferred_address Master Sam, prompt includes it."""
    p = UserProfile(speaker_id="x", display_name="Sam", address_style="master")
    out = build_c3po_system_prompt(p, mode="ambient")
    assert "Master Sam" in out
    p2 = UserProfile(speaker_id="x", preferred_address="Master Sam")
    out2 = build_c3po_system_prompt(p2, mode="ambient")
    assert "Master Sam" in out2


def test_default_prompt_constant() -> None:
    """DEFAULT_PROMPT is defined and contains THREEPIO."""
    assert "THREEPIO" in DEFAULT_PROMPT
