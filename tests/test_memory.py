"""Tests for ShortTermMemory."""

import pytest

from threepio.brain.memory import ShortTermMemory
from threepio.core.types import DialogueTurn


def test_memory_stores_turns() -> None:
    """Memory stores turns in order."""
    mem = ShortTermMemory(max_turns=3)
    mem.add(DialogueTurn(role="user", content="Hello"))
    mem.add(DialogueTurn(role="assistant", content="Hi there"))
    turns = mem.get_turns()
    assert len(turns) == 2
    assert turns[0].content == "Hello"
    assert turns[1].content == "Hi there"


def test_memory_trims_to_max_turns() -> None:
    """Memory keeps only last N turns."""
    mem = ShortTermMemory(max_turns=3)
    mem.add(DialogueTurn(role="user", content="1"))
    mem.add(DialogueTurn(role="assistant", content="2"))
    mem.add(DialogueTurn(role="user", content="3"))
    mem.add(DialogueTurn(role="assistant", content="4"))
    turns = mem.get_turns()
    assert len(turns) == 3
    assert turns[0].content == "2"
    assert turns[1].content == "3"
    assert turns[2].content == "4"


def test_memory_clear() -> None:
    """Clear empties all turns."""
    mem = ShortTermMemory(max_turns=5)
    mem.add(DialogueTurn(role="user", content="x"))
    mem.clear()
    assert len(mem.get_turns()) == 0


# ConversationMemory (rolling window)
def test_conversation_memory_rolling_window() -> None:
    """ConversationMemory keeps only last N turns."""
    from threepio.memory.memory import ConversationMemory

    mem = ConversationMemory(max_turns=3)
    mem.add_user("a")
    mem.add_assistant("1")
    mem.add_user("b")
    mem.add_assistant("2")
    mem.add_user("c")
    mem.add_assistant("3")
    mem.add_user("d")
    msgs = mem.as_messages("You are helpful.")
    assert msgs[0]["role"] == "system"
    turns = [m for m in msgs if m["role"] in ("user", "assistant")]
    assert len(turns) == 3
    assert turns[-1]["content"] == "d"
