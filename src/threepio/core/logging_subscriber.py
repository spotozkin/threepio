"""Logging subscriber for the droid event bus."""

from __future__ import annotations

import logging
import time
from typing import Callable

from threepio.core.state import DroidEvent

logger = logging.getLogger(__name__)


def create_logging_subscriber() -> Callable[[DroidEvent], None]:
    """Return a subscriber that logs each event: [event] t=<ts> type=<type> payload=<payload>."""

    def on_event(evt: DroidEvent) -> None:
        ts = evt.ts if evt.ts is not None else time.time()
        logger.debug(
            "[event] t=%s type=%s payload=%s",
            ts,
            evt.type,
            evt.payload,
        )

    return on_event
