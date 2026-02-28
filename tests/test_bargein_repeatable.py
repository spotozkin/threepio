"""
Prove: vad_bargein_confirmed requires ≥2 consecutive speech frames in the window;
VADMonitor in barge_in mode can trigger on_speech_start twice (unlatches correctly).
No real mic; use mocks and 960-byte frames.
"""

import threading
import time
from unittest.mock import patch

from threepio.audio.vad import (
    VAD_BYTES_PER_FRAME,
    VADMonitor,
    vad_bargein_confirmed,
)


def test_vad_bargein_confirmed_two_consecutive_speech_frames() -> None:
    """Tail with ≥2 consecutive speech frames => True; only 1 speech at end => False."""
    # 960-byte frames (matches VAD_BYTES_PER_FRAME)
    frame_silent = b"\x00" * VAD_BYTES_PER_FRAME
    frame_speech = (
        b"\xff" * (VAD_BYTES_PER_FRAME // 2) + b"\x00" * (VAD_BYTES_PER_FRAME // 2)
    )

    class MockVad:
        def is_speech(self, buf: bytes, sample_rate: int) -> bool:
            return buf == frame_speech

    # 4 frames total; tail ends with 2 consecutive speech => True
    frames_four = [frame_silent, frame_silent, frame_speech, frame_speech]
    with patch("threepio.audio.vad._get_vad", return_value=MockVad()):
        assert vad_bargein_confirmed(frames_four, confirm_frames=4) is True

    # Tail ends with only 1 speech frame => False
    frames_one_speech = [frame_silent, frame_silent, frame_speech]
    with patch("threepio.audio.vad._get_vad", return_value=MockVad()):
        assert vad_bargein_confirmed(frames_one_speech, confirm_frames=3) is False


def test_vadmonitor_bargein_can_trigger_twice() -> None:
    """VADMonitor in barge_in mode can fire on_speech_start twice in one run (unlatches)."""
    # 960-byte frames
    frame_speech = (
        b"\xff" * (VAD_BYTES_PER_FRAME // 2) + b"\x00" * (VAD_BYTES_PER_FRAME // 2)
    )
    frame_nonspeech = b"\x00" * VAD_BYTES_PER_FRAME

    # Burst 1: speech, speech | silence: nonspeech, nonspeech | Burst 2: speech, speech
    frames_list = [
        frame_speech,
        frame_speech,
        frame_nonspeech,
        frame_nonspeech,
        frame_speech,
        frame_speech,
    ]
    it = iter(frames_list)

    def read_frame() -> bytes | None:
        return next(it, None)

    on_speech_start_calls: list[int] = []
    lock = threading.Lock()

    def on_speech_start() -> None:
        with lock:
            on_speech_start_calls.append(1)

    def on_speech_end() -> None:
        pass

    class MockVad:
        def is_speech(self, buf: bytes, sample_rate: int) -> bool:
            return buf == frame_speech

    # Suppression already passed; small confirm window so 2 frames are enough
    with patch("threepio.audio.vad._get_vad", return_value=MockVad()), patch(
        "threepio.audio.vad.get_bargein_confirm_ms", return_value=60
    ):
        monitor = VADMonitor(
            read_frame=read_frame,
            on_speech_start=on_speech_start,
            on_speech_end=on_speech_end,
            mode="barge_in",
            frame_bytes=VAD_BYTES_PER_FRAME,
            frame_queue=None,
        )
        monitor.set_speaking_start_ts(time.time() - 10.0)
        monitor.start()

        # Wait for thread to consume all 6 frames (read_frame returns None) and exit
        deadline = time.monotonic() + 2.0
        while monitor._thread is not None and monitor._thread.is_alive():
            if time.monotonic() > deadline:
                break
            time.sleep(0.01)

    assert len(on_speech_start_calls) == 2, (
        f"on_speech_start should be called exactly 2 times, got {len(on_speech_start_calls)}"
    )
    assert monitor._thread is not None and not monitor._thread.is_alive(), (
        "Monitor thread should exit cleanly when frame source returns None"
    )
