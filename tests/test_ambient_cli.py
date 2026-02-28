"""Tests for --ambient CLI: help and that run_ambient is invoked (mock so no audio)."""

import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"


def test_help_includes_ambient_and_device_in() -> None:
    """--ambient, --device-in, --vad-threshold appear in CLI help."""
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "threepio.main", "-h"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        timeout=10,
    )
    assert result.returncode == 0
    assert "--ambient" in result.stdout
    assert "--device-in" in result.stdout
    assert "--vad-threshold" in result.stdout


def test_ambient_flag_calls_run_ambient_with_args() -> None:
    """--ambient with --device-in 1 calls run_ambient with device_in=1; mock so no real audio."""
    from threepio.main import main, _run_ambient

    with patch("threepio.main._run_ambient", return_value=0) as mock_run:
        with patch("sys.argv", ["main", "--ambient", "--device-in", "1"]):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0
            else:
                pytest.fail("main() should sys.exit after --ambient")
        mock_run.assert_called_once()
        call_args, call_kw = mock_run.call_args
        assert call_args[0] is not None  # settings
        assert call_kw.get("device_in") == 1
        assert "vad_threshold" in call_kw


def test_ambient_run_does_not_raise_when_user_profile_missing() -> None:
    """_load_user_profile_fns() returns fallbacks when threepio.memory.user_profile is missing."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "threepio.memory.user_profile":
            raise ModuleNotFoundError("No module named 'threepio.memory.user_profile'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        from threepio.modes.ambient import _load_user_profile_fns

        (
            get_preferred_address,
            load_profile,
            mark_addressed,
            save_profile,
            should_inject_address,
            update_from_user_text,
        ) = _load_user_profile_fns()
    assert load_profile() == {}
    assert load_profile("default", ".") == {}
    assert get_preferred_address({}) is None
    assert should_inject_address({}, 0.0, 90.0) is False
    mark_addressed({}, 0.0)
    assert update_from_user_text({}, "hi") == {}
    save_profile({}, ".")


def test_ambient_run_does_not_raise_when_c3po_governor_missing() -> None:
    """_load_classify_fn() returns fallback that allows replies when threepio.persona.c3po_governor is missing."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "threepio.persona.c3po_governor":
            raise ModuleNotFoundError("No module named 'threepio.persona.c3po_governor'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        from threepio.modes.ambient import _load_classify_fn

        classify = _load_classify_fn()
    assert callable(classify)
    assert classify("hello") == {"allow": True}


def test_ambient_run_does_not_raise_when_address_gating_missing() -> None:
    """_load_address_gating_fns() returns fallback that returns None when threepio.persona.address_gating is missing."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "threepio.persona.address_gating":
            raise ModuleNotFoundError("No module named 'threepio.persona.address_gating'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        from threepio.modes.ambient import _load_address_gating_fns

        extract_speaker_address = _load_address_gating_fns()
    assert callable(extract_speaker_address)
    assert extract_speaker_address("hello") is None
    assert extract_speaker_address("hello", "extra") is None


def test_ambient_run_does_not_raise_when_flavor_governor_missing() -> None:
    """_load_flavor_governor_fn() returns fallback that returns None when threepio.persona.flavor_governor is missing."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name: str, *args: object, **kwargs: object):
        if name == "threepio.persona.flavor_governor":
            raise ModuleNotFoundError("No module named 'threepio.persona.flavor_governor'")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", side_effect=fake_import):
        from threepio.modes.ambient import _load_flavor_governor_fn

        flavor_intent = _load_flavor_governor_fn()
    assert callable(flavor_intent)
    assert flavor_intent("hello") is None
