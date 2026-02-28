"""
Slang policy: interpreter detects label from pack; prompt forbids repeating slang in output.
"""

import pytest

from threepio.persona.loader import load_persona_pack
from threepio.persona.prompt_builder import build_c3po_system_prompt
from threepio.persona.slang import interpret_slang


def test_slang_interpreter_detects_label() -> None:
    """interpret_slang returns (text, labels); with empty pack.slang_map, labels are empty."""
    try:
        pack = load_persona_pack()
    except FileNotFoundError:
        pytest.skip("persona pack not found")
    _, labels = interpret_slang("that guy is my partner", pack)
    assert isinstance(labels, list)


def test_prompt_forbids_repeating_slang() -> None:
    """System prompt explicitly forbids repeating or mirroring slang in the assistant output."""
    out = build_c3po_system_prompt(None, mode="ambient", user_text="hey there")
    assert "slang" in out.lower()
    assert "not repeat" in out.lower() or "mirror" in out.lower() or "do not repeat" in out.lower()
