"""Tests for startup healthcheck (mocked which + filesystem)."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"

from threepio.core.healthcheck import (
    run_startup_checks,
    print_report,
    DATA_DIRS,
)
from threepio.speech.playback import get_resolved_playback_binary


def test_run_startup_checks_providers_summary(tmp_path: Path) -> None:
    """Report includes readable provider summary; mock which and writable dirs."""
    settings = MagicMock()
    settings.PROVIDER_TTS = "mock"
    settings.PROVIDER_STT = "mock"
    settings.PROVIDER_LLM = "mock"
    settings.AUDIO_OUTPUT_MODE = "print"
    settings.OPENAI_API_KEY = None

    def which(cmd: str):
        if cmd == "ffmpeg":
            return "/usr/bin/ffmpeg"
        return None

    report = run_startup_checks(settings, which_func=which, data_dirs=("data/tts",), cwd=tmp_path)
    assert "providers" in report
    assert report["providers"].get("tts") == "mock"
    assert report["providers"].get("stt") == "mock"
    assert report["dirs"].get("data/tts") is True
    assert report["binaries"]["playback"] == "print"
    assert report["ok"] is True


def test_run_startup_checks_elevenlabs_missing_raises() -> None:
    """PROVIDER_TTS=elevenlabs with missing env raises RuntimeError."""
    settings = MagicMock()
    settings.PROVIDER_TTS = "elevenlabs"
    settings.PROVIDER_STT = "mock"
    settings.PROVIDER_LLM = "mock"
    settings.AUDIO_OUTPUT_MODE = "print"
    settings.OPENAI_API_KEY = None

    with pytest.raises(RuntimeError) as exc_info:
        run_startup_checks(settings, which_func=lambda c: "/usr/bin/ffmpeg" if c == "ffmpeg" else None)
    assert "ELEVENLABS" in str(exc_info.value)


def test_run_startup_checks_elevenlabs_ok_with_env(tmp_path: Path) -> None:
    """PROVIDER_TTS=elevenlabs with Settings having ElevenLabs keys passes (mocked which + dirs)."""
    settings = MagicMock()
    settings.PROVIDER_TTS = "elevenlabs"
    settings.PROVIDER_STT = "mock"
    settings.PROVIDER_LLM = "mock"
    settings.AUDIO_OUTPUT_MODE = "print"
    settings.OPENAI_API_KEY = None
    settings.ELEVENLABS_API_KEY = "sk-x"
    settings.ELEVENLABS_VOICE_ID = "v1"
    settings.ELEVENLABS_MODEL_ID = "eleven_v2"

    report = run_startup_checks(
        settings,
        which_func=lambda c: "/usr/bin/ffmpeg" if c == "ffmpeg" else None,
        data_dirs=("data/tts",),
        cwd=tmp_path,
    )
    assert report["ok"] is True
    assert "ELEVENLABS" not in str(report.get("errors", []))


def test_run_startup_checks_stt_whisper_needs_openai_key(tmp_path: Path) -> None:
    """PROVIDER_STT=whisper with no OPENAI_API_KEY sets report ok=False and error."""
    settings = MagicMock()
    settings.PROVIDER_TTS = "mock"
    settings.PROVIDER_STT = "whisper"
    settings.PROVIDER_LLM = "mock"
    settings.AUDIO_OUTPUT_MODE = "print"
    settings.OPENAI_API_KEY = None

    report = run_startup_checks(
        settings,
        which_func=lambda c: "/usr/bin/ffmpeg" if c == "ffmpeg" else None,
        data_dirs=("data/tts",),
        cwd=tmp_path,
    )
    assert report["ok"] is False
    assert any("OPENAI_API_KEY" in e or "whisper" in e for e in report["errors"])


def test_run_startup_checks_ffmpeg_required_when_tts_real(tmp_path: Path) -> None:
    """When TTS is openai/elevenlabs and ffmpeg missing, report has error."""
    settings = MagicMock()
    settings.PROVIDER_TTS = "openai"
    settings.PROVIDER_STT = "mock"
    settings.PROVIDER_LLM = "mock"
    settings.AUDIO_OUTPUT_MODE = "print"
    settings.OPENAI_API_KEY = "sk-x"

    report = run_startup_checks(
        settings,
        which_func=lambda c: None,
        data_dirs=("data/tts",),
        cwd=tmp_path,
    )
    assert report["ok"] is False
    assert any("ffmpeg" in e.lower() for e in report["errors"])


def test_resolve_playback_binary_print_returns_none() -> None:
    """Mode print needs no binary."""
    assert get_resolved_playback_binary("print") is None


def test_resolve_playback_binary_auto_darwin_afplay() -> None:
    """Auto on darwin uses afplay when available."""
    from unittest.mock import patch
    if sys.platform != "darwin":
        pytest.skip("darwin only")
    with patch("threepio.speech.playback._which", side_effect=lambda c: "/usr/bin/afplay" if c == "afplay" else None):
        path = get_resolved_playback_binary("auto")
    assert path == "/usr/bin/afplay"


def test_resolve_playback_binary_ffplay_explicit() -> None:
    """Explicit ffplay returns ffplay when which finds it."""
    from unittest.mock import patch
    with patch("threepio.speech.playback._which", side_effect=lambda c: "/usr/bin/ffplay" if c == "ffplay" else None):
        path = get_resolved_playback_binary("ffplay")
    assert path == "/usr/bin/ffplay"


def test_run_startup_checks_dirs_not_writable(tmp_path: Path) -> None:
    """When a data dir cannot be created (e.g. path is a file), report dirs[rel]=False and ok=False."""
    settings = MagicMock()
    settings.PROVIDER_TTS = "mock"
    settings.PROVIDER_STT = "mock"
    settings.PROVIDER_LLM = "mock"
    settings.AUDIO_OUTPUT_MODE = "print"
    settings.OPENAI_API_KEY = None

    # Make "data_tts" a file so mkdir() will fail (portable, no chmod)
    (tmp_path / "data_tts").write_text("not-a-dir")

    report = run_startup_checks(
        settings,
        which_func=lambda c: "/usr/bin/ffmpeg" if c == "ffmpeg" else None,
        data_dirs=("data/tts", "data_tts"),
        cwd=tmp_path,
    )
    assert report["ok"] is False
    assert report["dirs"].get("data_tts") is False


def test_print_report_no_crash() -> None:
    """print_report does not crash."""
    report = {"ok": True, "providers": {"tts": "mock"}, "binaries": {"ffmpeg": True}, "dirs": {}, "errors": []}
    print_report(report)


def test_cli_help_includes_healthcheck() -> None:
    """--healthcheck appears in CLI help."""
    result = subprocess.run(
        [sys.executable, "-m", "threepio.main", "-h"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        timeout=10,
    )
    assert result.returncode == 0
    assert "--healthcheck" in result.stdout


def test_cli_healthcheck_exit_0_with_mock_providers() -> None:
    """--healthcheck exits 0 when providers are mock and data dirs writable (no machine deps)."""
    env = {
        **os.environ,
        "PYTHONPATH": str(_SRC),
        "PROVIDER_TTS": "mock",
        "PROVIDER_STT": "mock",
        "PROVIDER_LLM": "mock",
        "AUDIO_OUTPUT_MODE": "print",
    }
    result = subprocess.run(
        [sys.executable, "-m", "threepio.main", "--healthcheck"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env=env,
        timeout=15,
    )
    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "Healthcheck" in result.stdout
