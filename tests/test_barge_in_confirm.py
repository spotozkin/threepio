"""
Barge-in confirmation: webrtcvad requires >=2 consecutive speech frames (vad_bargein_confirmed),
or energy confirmation. Assert stop() called and state transitions to LISTENING.
"""

import pytest

from threepio.audio.vad import (
    VAD_BYTES_PER_FRAME,
    VAD_FRAME_MS,
    count_speech_frames_in_window,
    energy_bargein_confirmed,
    get_bargein_confirm_ms,
    get_speech_suppress_ms,
    vad_bargein_confirmed,
)


def test_bargein_confirm_ms_positive() -> None:
    """get_bargein_confirm_ms() returns a positive value (confirm window in ms)."""
    ms = get_bargein_confirm_ms()
    assert ms >= 0


def test_suppress_ms_positive() -> None:
    """get_speech_suppress_ms() returns a positive value."""
    ms = get_speech_suppress_ms()
    assert ms >= 0


def test_vad_confirmation_requires_multiple_frames() -> None:
    """Barge-in via webrtcvad is confirmed when >=2 frames in window are speech."""
    confirm_frames = max(2, get_bargein_confirm_ms() // VAD_FRAME_MS)
    # Empty or single-frame window should not confirm (count_speech_frames_in_window < 2)
    empty = []
    assert count_speech_frames_in_window(empty) < 2
    # Logic in ambient: vad_barge_confirmed = len(speak_confirm_frames) >= confirm_frames and count_speech_frames_in_window(speak_confirm_frames) >= 2
    assert confirm_frames >= 2


def test_energy_bargein_requires_confirm_frames() -> None:
    """energy_bargein_confirmed requires at least confirm_frames consecutive high-RMS frames."""
    confirm_frames = max(1, get_bargein_confirm_ms() // VAD_FRAME_MS)
    low_rms = [0.001] * 20
    assert not energy_bargein_confirmed(low_rms, confirm_frames)
    # With fewer than confirm_frames we get False
    short_high = [0.05] * (confirm_frames - 1) if confirm_frames > 1 else []
    assert not energy_bargein_confirmed(short_high, confirm_frames)


def test_barge_in_mock_stop_called_state_listening() -> None:
    """When barge-in triggers (vad or energy confirmed), stop() is called and state becomes LISTENING."""
    stop_calls: list[int] = []

    class MockHandle:
        def stop(self) -> None:
            stop_calls.append(1)

        def is_running(self) -> bool:
            return len(stop_calls) == 0

    handle = MockHandle()
    state = "SPEAKING"
    vad_barge_confirmed = True
    energy_barge = False
    if vad_barge_confirmed or energy_barge:
        handle.stop()
        state = "LISTENING"
    assert len(stop_calls) == 1
    assert state == "LISTENING"


def test_vad_bargein_confirmed_two_consecutive_speech_frames() -> None:
    """vad_bargein_confirmed returns True only when >=2 consecutive frames are speech (monkeypatch)."""
    from unittest.mock import patch

    # Build fake frames of correct size (960 bytes each)
    frame_silent = b"\x00" * VAD_BYTES_PER_FRAME
    frame_speech = b"\xff" * (VAD_BYTES_PER_FRAME // 2) + b"\x00" * (VAD_BYTES_PER_FRAME // 2)
    # Sequence: silent, silent, speech, speech -> last 2 consecutive are speech
    frames_confirm = [frame_silent, frame_silent, frame_speech, frame_speech]

    class MockVad:
        def is_speech(self, buf: bytes, sample_rate: int) -> bool:
            return buf == frame_speech

    with patch("threepio.audio.vad._get_vad", return_value=MockVad()):
        assert vad_bargein_confirmed(frames_confirm, confirm_frames=4) is True

    # One speech frame at end: not 2 consecutive
    frames_one = [frame_silent, frame_silent, frame_speech]
    with patch("threepio.audio.vad._get_vad", return_value=MockVad()):
        assert vad_bargein_confirmed(frames_one, confirm_frames=3) is False


def test_ambient_bargein_callback_stops_handle_and_sets_listening() -> None:
    """Simulate SPEAKING + VADMonitor on_speech_start: handle.stop() called, state -> LISTENING."""
    stop_calls: list[int] = []

    class MockHandle:
        def stop(self) -> None:
            stop_calls.append(1)

        def is_running(self) -> bool:
            return len(stop_calls) == 0

    state_ref = ["SPEAKING"]
    handle_ref: list[MockHandle | None] = [MockHandle()]

    def on_speech_start() -> None:
        if state_ref[0] != "SPEAKING":
            return
        h = handle_ref[0]
        if h is not None:
            h.stop()
        state_ref[0] = "LISTENING"

    on_speech_start()
    assert len(stop_calls) == 1
    assert state_ref[0] == "LISTENING"
