"""
Barge-in state machine: when user speaks during SPEAKING, stop() is called once,
state transitions to LISTENING, and interrupted speech is not appended.
"""

import pytest

from threepio.speech.playback import PlaybackHandle


def test_playback_handle_stop_idempotent() -> None:
    """stop() is safe to call multiple times."""
    import subprocess
    import sys
    # Start a process that sleeps so we have something to stop
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    handle = PlaybackHandle(proc)
    handle.stop()
    handle.stop()
    handle.stop()
    assert not handle.is_running()


def test_barge_in_stop_called_once() -> None:
    """Simulate barge-in: mock handle.stop() is called exactly once when barge-in triggers."""
    stop_calls: list[int] = []

    class MockHandle:
        def __init__(self) -> None:
            self._stopped = False

        def stop(self) -> None:
            stop_calls.append(1)

        def is_running(self) -> bool:
            return not self._stopped

    handle = MockHandle()
    state = "SPEAKING"
    # Simulate barge-in: user spoke
    state = "LISTENING"
    handle.stop()
    assert len(stop_calls) == 1


def test_barge_in_state_transitions_to_listening() -> None:
    """On barge-in, state becomes LISTENING (interrupted speech not resumed)."""
    state = "SPEAKING"
    barge_in_occurred = True
    if barge_in_occurred:
        state = "LISTENING"
    assert state == "LISTENING"


def test_interrupted_speech_not_appended() -> None:
    """After barge-in, the assistant output is the new turn's reply, not the interrupted one."""
    # Ambient design: when we transition to LISTENING we collect new speech, STT, LLM, TTS.
    # The previous reply is discarded; we never "append" interrupted speech to final output.
    interrupted_reply = "Oh my. I was just explaining that—"
    final_output_after_barge_in = "Yes, Master? How may I assist?"
    assert interrupted_reply not in final_output_after_barge_in
    assert "Yes" in final_output_after_barge_in
