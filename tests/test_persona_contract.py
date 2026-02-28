"""
Persona contract: prompt includes persona block, address rules, no-echo rule;
flavor governor effect for utility (max_asides=0, no name) and urgent (warn-then-steps, no asides).
"""

import pytest

from threepio.memory.user_profile import UserProfile
from threepio.persona.prompt_builder import build_c3po_system_prompt


def test_prompt_includes_persona_block() -> None:
    """Prompt includes persona block (from pack or fallback): voice/behavior/style."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "C-3PO" in out
    assert "formal" in out.lower()
    assert "sarcasm" in out.lower() or "slang" in out.lower()
    assert "aside" in out.lower() or "Do not echo" in out or "echo" in out.lower()


def test_prompt_includes_address_rules() -> None:
    """Prompt includes title/address rules: utility no name, relational at most once."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "address" in out.lower() or "title" in out.lower()
    assert "utility" in out.lower() or "factual" in out.lower()
    assert "do not use" in out.lower() or "without name" in out.lower() or "without title" in out.lower()


def test_prompt_includes_no_echo_rule() -> None:
    """Prompt explicitly forbids echoing or paraphrasing the user question."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "echo" in out.lower() or "paraphrase" in out.lower()
    assert "immediately" in out.lower() or "answer" in out.lower()


def test_flavor_utility_max_asides_zero_and_no_name() -> None:
    """For utility input, flavor sets max_asides=0 and prompt forbids name usage."""
    out = build_c3po_system_prompt(None, mode="ambient", user_text="What is the weather in London?")
    assert "max_asides=0" in out or "Do not use asides" in out or "no name" in out.lower()
    assert "utility" in out.lower() or "no name or title" in out.lower()


def test_flavor_urgent_warn_then_steps_no_asides() -> None:
    """For urgent input, prompt includes warn-then-steps and forbids asides."""
    out = build_c3po_system_prompt(
        None, mode="ambient", user_text="There is a gas smell in the kitchen"
    )
    assert "steps" in out.lower() or "safety" in out.lower() or "dangerous" in out.lower()
    assert "aside" in out.lower() or "max_asides=0" in out or "no asides" in out.lower()


def test_address_preferred_in_prompt_when_profile_has_address() -> None:
    """When profile has preferred address, prompt includes it."""
    profile = UserProfile(speaker_id="x", preferred_address="Master Sam")
    out = build_c3po_system_prompt(profile, mode="ambient")
    assert "Master Sam" in out
