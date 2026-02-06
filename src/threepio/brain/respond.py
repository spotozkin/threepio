"""Response generation (deterministic, no LLM)."""

from threepio.brain.persona import ThreepioPersona
from threepio.memory.memory import ConversationMemory
from threepio.tools.router import ToolRouter
from threepio.tools.types import ToolResult

QUIT_SIGNAL = "__QUIT__"
SYSTEM_PROMPT = "You are C-3PO, a polite protocol droid. Be helpful and courteous."


def _format_tool_results(
    results: list[ToolResult], persona: ThreepioPersona, user_text: str
) -> str:
    """Format tool results in persona voice."""
    parts: list[str] = []
    for r in results:
        if not r.ok:
            parts.append(persona.format_error(r.error or "Unknown error."))
            continue
        parts.append(persona.format_tool_response(r.tool_name, r.data, user_text))
    if len(parts) == 1:
        return parts[0]
    return " ".join(parts)


class Responder:
    """Generates responses from user text and tools (no LLM)."""

    def __init__(
        self,
        memory: ConversationMemory,
        tool_router: ToolRouter,
        persona: ThreepioPersona | None = None,
    ) -> None:
        self._memory = memory
        self._tool_router = tool_router
        self._persona = persona or ThreepioPersona()

    def respond(self, user_text: str) -> str:
        """Return response or __QUIT__."""
        if user_text.strip().lower() == "quit":
            return QUIT_SIGNAL

        specs = self._tool_router.route(user_text)
        results = self._tool_router.execute(specs)

        if results:
            reply = _format_tool_results(results, self._persona, user_text)
            if reply:
                return reply
        return self._persona.format_generic_response(user_text)
