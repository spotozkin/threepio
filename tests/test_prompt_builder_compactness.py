"""
Prompt builder compactness: system prompt contains no-echo rule, slang not mirrored,
address gating block, persona block from pack; urgent intent produces no asides and warn-then-steps.
"""

import pytest

from threepio.persona.prompt_builder import build_c3po_system_prompt


def test_system_prompt_contains_no_echo_rule() -> None:
    """System prompt includes rule: do not echo or paraphrase user question."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "echo" in out.lower() or "paraphrase" in out.lower()
    assert "immediately" in out.lower() or "answer" in out.lower()


def test_system_prompt_slang_not_mirrored_rule() -> None:
    """System prompt includes rule to not repeat or mirror slang."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "slang" in out.lower()
    assert "not repeat" in out.lower() or "mirror" in out.lower() or "do not" in out.lower()


def test_system_prompt_contains_address_gating_block() -> None:
    """System prompt includes address/title gating block."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "address" in out.lower() or "title" in out.lower()
    assert "utility" in out.lower() or "factual" in out.lower()


def test_system_prompt_contains_persona_block() -> None:
    """System prompt includes persona block (from pack or fallback): formal, no sarcasm."""
    out = build_c3po_system_prompt(None, mode="ambient")
    assert "C-3PO" in out
    assert "formal" in out.lower()
    assert "protocol droid" in out.lower() or "aside" in out.lower()


def test_urgent_intent_no_asides_warn_then_steps() -> None:
    """For urgent intent, prompt includes no asides and warn-then-steps language."""
    out = build_c3po_system_prompt(
        None, mode="ambient", user_text="There is a gas smell in the kitchen"
    )
    assert "aside" in out.lower() and ("max_asides=0" in out or "no asides" in out.lower())
    assert "steps" in out.lower() or "safety" in out.lower() or "dangerous" in out.lower()
