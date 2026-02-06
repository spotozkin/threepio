"""Short-term dialogue memory."""

from threepio.core.types import DialogueTurn


class ShortTermMemory:
    """Keeps the last N dialogue turns."""

    def __init__(self, max_turns: int = 5) -> None:
        self._max_turns = max_turns
        self._turns: list[DialogueTurn] = []

    def add(self, turn: DialogueTurn) -> None:
        """Append a turn and trim if over limit."""
        self._turns.append(turn)
        while len(self._turns) > self._max_turns:
            self._turns.pop(0)

    def get_turns(self) -> list[DialogueTurn]:
        """Return recent turns (oldest first)."""
        return list(self._turns)

    def clear(self) -> None:
        """Clear all turns."""
        self._turns.clear()
