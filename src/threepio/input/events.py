"""Input event types."""

import time
from dataclasses import dataclass
from enum import Enum


class EventType(str, Enum):
    """Input event types."""

    TEXT = "TEXT"
    BUTTON = "BUTTON"
    ENCODER = "ENCODER"


@dataclass
class InputEvent:
    """An input event."""

    type: EventType
    payload: dict
    ts: float
