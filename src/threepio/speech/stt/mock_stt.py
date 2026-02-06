"""Mock STT that returns a pre-provided line (for terminal demo)."""

from threepio.speech.stt.base import BaseSTT


class MockSTT(BaseSTT):
    """Mock STT: returns the line passed to set_line()."""

    def __init__(self) -> None:
        self._line: str = ""

    def set_line(self, line: str) -> None:
        """Set the line to return from listen()."""
        self._line = line

    def listen(self) -> str:
        """Return the line previously set via set_line()."""
        return self._line
