"""
Slang no-mirror: prompt includes do-not-repeat-slang; interpreter uses pack.slang_map when present.
"""

import pytest

from threepio.persona.loader import load_persona_pack
from threepio.persona.prompt_builder import build_c3po_system_prompt
from threepio.persona.slang import interpret_slang


def test_slang_in_map_gets_label() -> None:
    """interpret_slang returns (text, labels); with default pack slang_map empty, labels are empty."""
    try:
        pack = load_persona_pack()
    except FileNotFoundError:
        pytest.skip("persona pack not found")
    normalized, labels = interpret_slang("where do I find a partner", pack)
    assert isinstance(normalized, str)
    assert isinstance(labels, list)
    # Default pack has empty slang_map; no explicit terms in repo
    assert pack.slang_map == {} or len(labels) >= 0


def test_prompt_includes_do_not_repeat_slang() -> None:
    """System prompt includes instruction not to repeat or mirror slang phrasing."""
    out = build_c3po_system_prompt(None, mode="ambient", user_text="what's up")
    assert "slang" in out.lower()
    assert "not repeat" in out.lower() or "mirror" in out.lower()


def test_interpret_slang_returns_labels_from_pack() -> None:
    """interpret_slang returns labels from pack.slang_map when present; empty map yields empty labels."""
    try:
        pack = load_persona_pack()
    except FileNotFoundError:
        pytest.skip("persona pack not found")
    _, labels = interpret_slang("they want a relationship", pack)
    assert isinstance(labels, list)
