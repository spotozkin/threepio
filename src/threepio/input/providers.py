"""Input providers."""

import time

from threepio.input.events import EventType, InputEvent


class InputProvider:
    """Base input provider."""

    def get_event_blocking(self) -> InputEvent:
        """Block until next event."""
        raise NotImplementedError


class ConsoleInputProvider(InputProvider):
    """Reads text from console with 'You: ' prompt."""

    def get_event_blocking(self) -> InputEvent:
        try:
            text = input("You: ").strip()
        except EOFError:
            text = "quit"
        return InputEvent(
            type=EventType.TEXT,
            payload={"text": text},
            ts=time.time(),
        )
