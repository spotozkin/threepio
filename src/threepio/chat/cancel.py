"""Cancellation primitives for barge-in and interruptible operations."""

from __future__ import annotations

import threading


class CancelScope:
    """Simple cancellation token. Call cancel() to signal cancellation."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled = False

    def cancel(self) -> None:
        """Mark this scope as cancelled."""
        with self._lock:
            self._cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """True if cancel() was called."""
        with self._lock:
            return self._cancelled

    def reset(self) -> None:
        """Clear cancelled state (for reuse)."""
        with self._lock:
            self._cancelled = False
