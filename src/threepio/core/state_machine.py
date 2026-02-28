"""Minimal state machine that subscribes to the event bus. Placeholder for future logic."""

from __future__ import annotations

from threepio.core.events import EventBus
from threepio.core.state import DroidEvent


class StateMachine:
    """Subscribes to EventBus; on_event is a no-op placeholder for future behavior."""

    def __init__(self, bus: EventBus) -> None:
        bus.subscribe(self.on_event)

    def on_event(self, evt: DroidEvent) -> None:
        """Handle an event. No-op placeholder for future state transitions."""
        pass
