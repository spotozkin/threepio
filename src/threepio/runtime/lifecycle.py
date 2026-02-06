"""Lifecycle manager: state transitions and cleanup hooks."""

import logging
from typing import Callable, NoReturn

from threepio.runtime.state import SystemState

logger = logging.getLogger(__name__)


class LifecycleManager:
    """Manages system state and ensures cleanup on shutdown."""

    def __init__(self) -> None:
        self._state = SystemState.BOOTING
        self._cleanup_callbacks: list[Callable[[], None]] = []
        self._shutdown_run = False

    @property
    def state(self) -> SystemState:
        return self._state

    def set_state(self, new_state: SystemState) -> None:
        """Transition to new state with logging."""
        old = self._state
        self._state = new_state
        logger.info("State: %s -> %s", old.value, new_state.value)

    def register_cleanup(self, callback: Callable[[], None]) -> None:
        """Register a callback to run on shutdown."""
        self._cleanup_callbacks.append(callback)

    def run_cleanup(self) -> None:
        """Run all cleanup callbacks (idempotent)."""
        if self._shutdown_run:
            return
        self._shutdown_run = True
        self.set_state(SystemState.SHUTDOWN)
        for cb in self._cleanup_callbacks:
            try:
                cb()
            except Exception as e:
                logger.exception("Cleanup callback failed: %s", e)
