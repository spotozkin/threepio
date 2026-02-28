"""Settings defaults: ensure optional/ambient-related attributes exist with safe defaults."""

import pytest

from threepio.config import get_settings


def test_settings_has_enable_c3po_fx() -> None:
    """Settings has ENABLE_C3PO_FX attribute; default is False."""
    settings = get_settings()
    assert hasattr(settings, "ENABLE_C3PO_FX")
    assert settings.ENABLE_C3PO_FX is False


def test_settings_has_stt_and_min_utterance() -> None:
    """Settings has STT_* and MIN_UTTERANCE_SEC; defaults are safe for ambient."""
    settings = get_settings()
    assert hasattr(settings, "STT_LANGUAGE")
    assert hasattr(settings, "STT_MODEL")
    assert hasattr(settings, "STT_BEAM_SIZE")
    assert hasattr(settings, "MIN_UTTERANCE_SEC")
    assert settings.STT_MODEL in ("tiny", "base", "small", "medium", "large-v3") or isinstance(settings.STT_MODEL, str)
    assert 0.1 <= settings.MIN_UTTERANCE_SEC <= 30.0
