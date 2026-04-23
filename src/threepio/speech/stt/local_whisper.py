"""Local Whisper STT using faster-whisper."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lazy model singleton
_model = None
_model_size: str | None = None


def ensure_model_loaded(model_size: str = "tiny.en") -> None:
    """Load the Whisper model if not already cached for ``model_size``."""
    global _model, _model_size
    if _model is not None and _model_size == model_size:
        return
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError(
            "faster-whisper not installed. pip install faster-whisper"
        ) from e
    logger.info("[local_whisper] loading model %s", model_size)
    _model = WhisperModel(model_size, device="cpu", compute_type="int8")
    _model_size = model_size


def transcribe(
    path: Path,
    *,
    model_size: str = "small",
    language: str | None = None,
    beam_size: int = 5,
) -> tuple[str, Any]:
    """Transcribe WAV/audio file to text using faster-whisper.

    Returns (text, info) where info has .language (detected or requested).
    Raises RuntimeError if faster-whisper is not installed.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")
    ensure_model_loaded(model_size)
    segments, info = _model.transcribe(str(path), language=language, beam_size=beam_size)
    text = " ".join(s.text.strip() for s in segments if s.text).strip()
    return (text, info)
