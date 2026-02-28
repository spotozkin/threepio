"""Core event type for the droid event bus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DroidEvent:
    """Immutable event emitted on the EventBus."""

    type: str
    payload: dict[str, Any] | None = None
    ts: float | None = None
