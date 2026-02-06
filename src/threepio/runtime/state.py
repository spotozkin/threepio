"""System state enum."""

from enum import Enum


class SystemState(str, Enum):
    """THREEPIO runtime states."""

    BOOTING = "BOOTING"
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    THINKING = "THINKING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"
    SHUTDOWN = "SHUTDOWN"
