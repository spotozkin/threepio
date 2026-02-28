"""Tests for C-3PO FX: settings and filter chains (no real ffmpeg)."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest

from threepio.config import get_settings


def test_settings_include_c3po_fx_intensity() -> None:
    """Settings has C3PO_FX_INTENSITY with a numeric default; no AttributeError."""
    settings = get_settings()
    assert hasattr(settings, "C3PO_FX_INTENSITY")
    val = settings.C3PO_FX_INTENSITY
    assert isinstance(val, (int, float))
    assert 0 <= val <= 2


def test_settings_include_c3po_fx_style() -> None:
    """Settings has C3PO_FX_STYLE ab_fix1 | robot_v1."""
    settings = get_settings()
    assert hasattr(settings, "C3PO_FX_STYLE")
    assert settings.C3PO_FX_STYLE in ("ab_fix1", "robot_v1")


def test_settings_include_all_c3po_fx_params() -> None:
    """All C3PO_* params referenced by c3po_fx are present on Settings."""
    settings = get_settings()
    attrs = [
        "C3PO_FX_STYLE",
        "C3PO_FX_INTENSITY",
        "C3PO_FX_VOLUME",
        "C3PO_FX_HIGHPASS",
        "C3PO_FX_LOWPASS",
        "C3PO_FX_COMP_THRESHOLD_DB",
        "C3PO_FX_COMP_RATIO",
        "C3PO_FX_COMP_ATTACK",
        "C3PO_FX_COMP_RELEASE",
        "C3PO_ECHO_IN",
        "C3PO_ECHO_OUT",
        "C3PO_ECHO_DELAYS",
        "C3PO_ECHO_DECAYS",
        "C3PO_LIMIT",
    ]
    for name in attrs:
        assert hasattr(settings, name), f"Settings missing {name}"


def test_c3po_fx_version_exists() -> None:
    """C3PO_FX_VERSION is defined for lock-in and regression tracking."""
    from threepio.speech.tts import c3po_fx

    assert hasattr(c3po_fx, "C3PO_FX_VERSION")
    assert isinstance(c3po_fx.C3PO_FX_VERSION, str)
    assert c3po_fx.C3PO_FX_VERSION.startswith("v")


def test_ab_fix1_chain_canonical_structure() -> None:
    """ab_fix1 chain at intensity=1.0 contains highpass=110, lowpass=12000, aecho 14|28, alimiter=0.95."""
    from threepio.speech.tts.c3po_fx import build_c3po_fx_chain

    with patch("threepio.speech.tts.c3po_fx._get_c3po_params") as mock_params:
        from threepio.speech.tts.c3po_fx import (
            AB_FIX1_ECHO_DECAYS,
            AB_FIX1_ECHO_DELAYS,
            AB_FIX1_HIGHPASS,
            AB_FIX1_LIMIT,
            AB_FIX1_LOWPASS,
            _db_to_linear_threshold,
        )
        comp_linear = _db_to_linear_threshold(-20.0)
        mock_params.return_value = {
            "volume": 0.95,
            "highpass": AB_FIX1_HIGHPASS,
            "lowpass": AB_FIX1_LOWPASS,
            "comp_threshold": comp_linear,
            "comp_ratio": 3,
            "comp_attack": 5,
            "comp_release": 90,
            "echo_in": 0.6,
            "echo_out": 0.75,
            "echo_delays": AB_FIX1_ECHO_DELAYS,
            "echo_decays": AB_FIX1_ECHO_DECAYS,
            "limit": AB_FIX1_LIMIT,
            "style": "ab_fix1",
        }
        chain = build_c3po_fx_chain(intensity=1.0, speed=1.0)

    assert f"highpass=f={AB_FIX1_HIGHPASS}" in chain
    assert f"lowpass=f={AB_FIX1_LOWPASS}" in chain
    assert "14|28" in chain
    assert "alimiter=limit=0.95" in chain


def test_ab_fix1_chain_signature_matches_canonical() -> None:
    """Generated ab_fix1 chain at intensity=1.0 matches CANONICAL_AB_FIX1_SIGNATURE (no real ffmpeg)."""
    from threepio.speech.tts.c3po_fx import (
        CANONICAL_AB_FIX1_SIGNATURE,
        build_c3po_fx_chain,
        get_ab_fix1_chain_signature,
    )

    with patch("threepio.speech.tts.c3po_fx._get_c3po_params") as mock_params:
        from threepio.speech.tts.c3po_fx import (
            AB_FIX1_ECHO_DECAYS,
            AB_FIX1_ECHO_DELAYS,
            AB_FIX1_HIGHPASS,
            AB_FIX1_LIMIT,
            AB_FIX1_LOWPASS,
            _db_to_linear_threshold,
        )
        comp_linear = _db_to_linear_threshold(-20.0)
        mock_params.return_value = {
            "volume": 0.95,
            "highpass": AB_FIX1_HIGHPASS,
            "lowpass": AB_FIX1_LOWPASS,
            "comp_threshold": comp_linear,
            "comp_ratio": 3,
            "comp_attack": 5,
            "comp_release": 90,
            "echo_in": 0.6,
            "echo_out": 0.75,
            "echo_delays": AB_FIX1_ECHO_DELAYS,
            "echo_decays": AB_FIX1_ECHO_DECAYS,
            "limit": AB_FIX1_LIMIT,
            "style": "ab_fix1",
        }
        chain = build_c3po_fx_chain(intensity=1.0, speed=1.0)
        sig = get_ab_fix1_chain_signature()
    assert sig == chain
    assert sig == CANONICAL_AB_FIX1_SIGNATURE


def test_acompressor_threshold_in_valid_range() -> None:
    """Filter chain acompressor threshold is linear and in ffmpeg valid range [0.000976563, 1.0]."""
    from threepio.speech.tts.c3po_fx import (
        ACCOMPRESSOR_THRESHOLD_MAX,
        ACCOMPRESSOR_THRESHOLD_MIN,
        build_c3po_fx_chain,
    )

    chain = build_c3po_fx_chain(intensity=1.0, speed=1.0)
    m = re.search(r"acompressor=threshold=([\d.]+)", chain)
    assert m is not None, f"acompressor threshold not found in chain: {chain}"
    threshold = float(m.group(1))
    assert ACCOMPRESSOR_THRESHOLD_MIN <= threshold <= ACCOMPRESSOR_THRESHOLD_MAX, (
        f"acompressor threshold {threshold} outside [{ACCOMPRESSOR_THRESHOLD_MIN}, {ACCOMPRESSOR_THRESHOLD_MAX}]"
    )


def test_robot_v1_chain_includes_ringmod_and_chorus() -> None:
    """robot_v1 chain includes ringmod and chorus (no real ffmpeg)."""
    from threepio.speech.tts.c3po_fx import build_c3po_fx_chain

    with patch("threepio.speech.tts.c3po_fx._get_c3po_params") as mock_params:
        from threepio.speech.tts.c3po_fx import _db_to_linear_threshold

        comp_linear = _db_to_linear_threshold(-20.0)
        mock_params.return_value = {
            "volume": 0.95,
            "highpass": 110,
            "lowpass": 12000,
            "comp_threshold": comp_linear,
            "comp_ratio": 3,
            "comp_attack": 5,
            "comp_release": 90,
            "echo_in": 0.6,
            "echo_out": 0.75,
            "echo_delays": "14|28",
            "echo_decays": "0.18|0.12",
            "limit": 0.95,
            "style": "robot_v1",
        }
        chain = build_c3po_fx_chain(intensity=1.0, speed=1.0)

    assert "ringmod=" in chain
    assert "chorus=" in chain


def test_apply_c3po_fx_reads_intensity_no_attribute_error(tmp_path: Path) -> None:
    """apply_c3po_fx runs without AttributeError; ffmpeg mocked; atomic write via temp then rename."""
    raw_wav = tmp_path / "raw.wav"
    out_mp3 = tmp_path / "out.mp3"
    raw_wav.write_bytes(b"\x00" * 1000)

    with patch("threepio.speech.tts.c3po_fx.subprocess.run") as mock_run:
        mock_run.return_value = type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        from threepio.speech.tts.c3po_fx import apply_c3po_fx

        # apply_c3po_fx writes to stem.tmp.suffix then renames; create temp so replace() succeeds
        (tmp_path / "out.tmp.mp3").write_bytes(b"\x00" * 200)
        result_chain = apply_c3po_fx(str(raw_wav), str(out_mp3))
        assert isinstance(result_chain, str)
        assert "volume=" in result_chain
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "ffmpeg" in call_args
        assert "-af" in call_args
        assert "-c:a" in call_args
        assert "libmp3lame" in call_args
        # Output is written to temp then renamed; argv contains the temp path
        assert any(".tmp." in str(a) for a in call_args)
        assert out_mp3.exists()
        assert out_mp3.stat().st_size >= 128
