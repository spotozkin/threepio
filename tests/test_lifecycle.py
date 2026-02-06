"""Tests for lifecycle cleanup callbacks."""

import pytest

from threepio.runtime.lifecycle import LifecycleManager
from threepio.runtime.state import SystemState


def test_cleanup_callbacks_invoked() -> None:
    """Cleanup callbacks are run on run_cleanup()."""
    ran: list[int] = []
    lm = LifecycleManager()
    lm.register_cleanup(lambda: ran.append(1))
    lm.register_cleanup(lambda: ran.append(2))
    lm.run_cleanup()
    assert ran == [1, 2]
    assert lm.state == SystemState.SHUTDOWN


def test_cleanup_idempotent() -> None:
    """run_cleanup is idempotent."""
    count = 0

    def inc() -> None:
        nonlocal count
        count += 1

    lm = LifecycleManager()
    lm.register_cleanup(inc)
    lm.run_cleanup()
    lm.run_cleanup()
    assert count == 1
