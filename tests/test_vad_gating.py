"""Tests for VAD speech_start gating predicate (RMS gate) and should_accept_speech."""

import pytest

from threepio.audio.vad import (
    get_vad_cooldown_ms,
    get_vad_start_rms,
    should_accept_speech,
    vad_speech_start_allowed,
)


def test_speech_start_disallowed_when_no_vad_or_energy() -> None:
    """When neither vad nor energy detect start, predicate is False regardless of RMS."""
    assert vad_speech_start_allowed(False, False, 0.01, 0.004) is False
    assert vad_speech_start_allowed(False, False, 0.0, 0.004) is False


def test_speech_start_allowed_when_rms_at_or_above_threshold() -> None:
    """When vad or energy detect start and RMS >= threshold, predicate is True."""
    assert vad_speech_start_allowed(True, False, 0.004, 0.004) is True
    assert vad_speech_start_allowed(True, False, 0.005, 0.004) is True
    assert vad_speech_start_allowed(False, True, 0.01, 0.004) is True


def test_speech_start_gated_when_rms_below_threshold() -> None:
    """When vad or energy detect start but RMS < threshold, predicate is False."""
    assert vad_speech_start_allowed(True, False, 0.003, 0.004) is False
    assert vad_speech_start_allowed(False, True, 0.002, 0.004) is False
    assert vad_speech_start_allowed(True, True, 0.0, 0.004) is False


def test_speech_start_threshold_zero_allows_any_nonzero_rms() -> None:
    """When threshold is 0, any (vad or energy) + non-negative RMS is allowed."""
    assert vad_speech_start_allowed(True, False, 0.0, 0.0) is True
    assert vad_speech_start_allowed(True, False, 0.001, 0.0) is True


def test_get_vad_start_rms_default() -> None:
    """get_vad_start_rms returns a non-negative float (default 0.004 when env unset)."""
    rms = get_vad_start_rms()
    assert isinstance(rms, float)
    assert rms >= 0.0


def test_get_vad_cooldown_ms_non_negative() -> None:
    """get_vad_cooldown_ms returns a non-negative int (default 400 when env unset)."""
    ms = get_vad_cooldown_ms()
    assert isinstance(ms, int)
    assert ms >= 0


# ---- should_accept_speech(is_vad_speech, rms, now_ms, last_reject_ms, start_rms, cooldown_ms) ----


def test_should_accept_speech_low_rms_rejection() -> None:
    """Rejected when VAD says speech but RMS < start_rms."""
    # is_vad_speech=True, rms=0.003 < 0.004 -> False
    assert should_accept_speech(True, 0.003, 100_000, 0, 0.004, 400) is False
    assert should_accept_speech(True, 0.0, 100_000, 0, 0.004, 400) is False


def test_should_accept_speech_cooldown_rejection() -> None:
    """Rejected when in cooldown (now_ms - last_reject_ms < cooldown_ms)."""
    last_reject = 100_000
    cooldown_ms = 400
    # now = 100_100 -> elapsed 100 ms < 400 -> reject
    assert should_accept_speech(True, 0.01, 100_100, last_reject, 0.004, cooldown_ms) is False
    # now = 100_399 -> still in cooldown
    assert should_accept_speech(True, 0.01, 100_399, last_reject, 0.004, cooldown_ms) is False


def test_should_accept_speech_acceptance() -> None:
    """Accepted when VAD speech, RMS >= threshold, and not in cooldown (or last_reject_ms=0)."""
    assert should_accept_speech(True, 0.005, 100_000, 0, 0.004, 400) is True
    assert should_accept_speech(True, 0.004, 100_000, 0, 0.004, 400) is True
    # Out of cooldown: last_reject=100_000, now=100_500, cooldown=400 -> elapsed 500 >= 400
    assert should_accept_speech(True, 0.01, 100_500, 100_000, 0.004, 400) is True


def test_should_accept_speech_no_vad_no_accept() -> None:
    """When is_vad_speech is False, never accept regardless of RMS."""
    assert should_accept_speech(False, 0.01, 100_000, 0, 0.004, 400) is False


def test_should_accept_speech_cooldown_zero_allows() -> None:
    """When cooldown_ms is 0, cooldown does not reject."""
    assert should_accept_speech(True, 0.01, 100_100, 100_000, 0.004, 0) is True
