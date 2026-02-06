"""Dialogue orchestration."""

from threepio.brain.llm.base import BaseLLM
from threepio.brain.memory import ShortTermMemory
from threepio.core.types import DialogueTurn


def generate_response(
    llm: BaseLLM,
    memory: ShortTermMemory,
    user_input: str,
) -> str:
    """Generate assistant response using LLM and memory context."""
    memory.add(DialogueTurn(role="user", content=user_input))
    context = memory.get_turns()[:-1]  # Exclude current user turn
    response = llm.generate(user_input=user_input, context=context)
    memory.add(DialogueTurn(role="assistant", content=response))
    return response
