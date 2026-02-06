"""Tests for voice dataset schema."""

import pytest

from threepio.voice.dataset.schema import VoiceSampleRow, parse_metadata_line


def test_parse_metadata_line_valid() -> None:
    """Parse valid metadata line."""
    row = parse_metadata_line("wavs/sample_001.wav|Hello world")
    assert row is not None
    assert row.audio_path == "wavs/sample_001.wav"
    assert row.transcript == "Hello world"
    assert row.duration_sec is None


def test_parse_metadata_line_with_duration() -> None:
    """Parse line with duration."""
    row = parse_metadata_line("wavs/sample_001.wav|Hello world|3.5")
    assert row is not None
    assert row.duration_sec == 3.5


def test_parse_metadata_line_empty_returns_none() -> None:
    """Empty or comment lines return None."""
    assert parse_metadata_line("") is None
    assert parse_metadata_line("   ") is None
    assert parse_metadata_line("# comment") is None


def test_parse_metadata_line_invalid_returns_none() -> None:
    """Line with only one part returns None."""
    assert parse_metadata_line("just_path") is None


def test_voice_sample_row_validates_transcript_non_empty() -> None:
    """VoiceSampleRow rejects empty transcript."""
    with pytest.raises(ValueError):
        VoiceSampleRow(audio_path="x.wav", transcript="")
