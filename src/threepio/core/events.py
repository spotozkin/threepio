"""Thread-safe synchronous event bus for droid events."""

from __future__ import annotations

import logging
import threading
from typing import Callable

from threepio.core.state import DroidEvent

logger = logging.getLogger(__name__)

Subscriber = Callable[[DroidEvent], None]


class EventBus:
    """Synchronous event bus. subscribe() adds a subscriber; emit() calls all. Thread-safe."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        """Add a subscriber callable. Signature: (evt: DroidEvent) -> None."""
        with self._lock:
            self._subscribers.append(fn)

    def emit(self, event: DroidEvent) -> None:
        """Call all subscribers with event. Swallow and log subscriber exceptions."""
        with self._lock:
            subs = list(self._subscribers)
        for fn in subs:
            try:
                fn(event)
            except Exception as e:
                logger.debug("EventBus subscriber error: %s", e, exc_info=True)
