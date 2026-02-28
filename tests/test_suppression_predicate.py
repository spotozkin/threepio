"""Tests for the speaking suppression predicate (barge-in / VAD finalization window)."""

import pytest

from threepio.audio.vad import is_speaking_suppression_active


def test_suppression_inactive_when_no_start_ts() -> None:
    """Suppression is False when speaking_start_ts is None."""
    assert is_speaking_suppression_active(1000.0, None, 600) is False


def test_suppression_inactive_when_suppress_ms_zero() -> None:
    """Suppression is False when suppress_ms <= 0."""
    assert is_speaking_suppression_active(1000.0, 999.0, 0) is False
    assert is_speaking_suppression_active(1000.0, 999.0, -100) is False


def test_suppression_active_immediately_after_start() -> None:
    """Suppression is True at the exact moment playback starts (elapsed 0 ms)."""
    start = 1000.0
    assert is_speaking_suppression_active(start, start, 600) is True


def test_suppression_active_within_window() -> None:
    """Suppression is True while elapsed < suppress_ms."""
    start = 1000.0
    # 500 ms later, window 600 ms -> still active
    assert is_speaking_suppression_active(1000.5, start, 600) is True
    # 599 ms later
    assert is_speaking_suppression_active(1000.599, start, 600) is True


def test_suppression_inactive_after_window() -> None:
    """Suppression is False once elapsed >= suppress_ms."""
    start = 1000.0
    # 600 ms later -> just outside 600 ms window
    assert is_speaking_suppression_active(1000.6, start, 600) is False
    assert is_speaking_suppression_active(1001.0, start, 600) is False
