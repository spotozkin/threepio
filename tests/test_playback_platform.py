"""Tests for cross-platform playback: auto must not select afplay on non-darwin."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from threepio.speech.playback import get_audio_output_mode, resolve_playback_mode


def test_auto_on_linux_does_not_return_afplay(tmp_path: Path) -> None:
    """On non-darwin, mode 'auto' must not resolve to afplay."""
    path = tmp_path / "test.wav"
    path.write_bytes(b"\x00")  # path must exist for resolution to run

    def which_impl(cmd: str) -> str | None:
        if cmd == "ffplay":
            return "/usr/bin/ffplay"
        if cmd == "afplay":
            return "/usr/bin/afplay"  # even if afplay existed on Linux, we must not use it
        return None

    with patch("sys.platform", "linux"):
        with patch("threepio.speech.playback._which", side_effect=which_impl):
            resolved = resolve_playback_mode("auto", path)
    assert resolved != "afplay", "auto on Linux must not select afplay"
    assert resolved == "ffplay"


def test_auto_on_linux_no_ffplay_uses_aplay_or_mpg123(tmp_path: Path) -> None:
    """On Linux with no ffplay, auto can resolve to aplay (for wav) or mpg123."""
    path = tmp_path / "test.wav"
    path.write_bytes(b"\x00")

    def which_impl(cmd: str) -> str | None:
        if cmd == "aplay":
            return "/usr/bin/aplay"
        return None

    with patch("sys.platform", "linux"):
        with patch("threepio.speech.playback._which", side_effect=which_impl):
            resolved = resolve_playback_mode("auto", path)
    assert resolved != "afplay"
    assert resolved == "aplay"


def test_auto_on_darwin_can_return_afplay(tmp_path: Path) -> None:
    """On darwin, auto may return afplay when available."""
    path = tmp_path / "test.mp3"
    path.write_bytes(b"\x00")

    def which_impl(cmd: str) -> str | None:
        if cmd == "afplay":
            return "/usr/bin/afplay"
        return None

    with patch("sys.platform", "darwin"):
        with patch("threepio.speech.playback._which", side_effect=which_impl):
            resolved = resolve_playback_mode("auto", path)
    assert resolved == "afplay"


def test_audio_playback_module_exports_get_audio_output_mode() -> None:
    """threepio.audio.playback re-exports get_audio_output_mode (no ImportError)."""
    mode = get_audio_output_mode()
    assert isinstance(mode, str)
    assert mode in ("auto", "afplay", "ffplay", "aplay", "mpg123", "print")
