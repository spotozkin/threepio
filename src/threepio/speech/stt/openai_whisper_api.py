"""OpenAI Whisper API STT provider."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class OpenAIWhisperAPIError(Exception):
    """Raised when Whisper API call fails."""


def transcribe(
    wav_path: str | Path,
    api_key: str,
    model: str = "whisper-1",
) -> str:
    """Transcribe WAV file via OpenAI Whisper API. Returns text."""
    path = Path(wav_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")

    try:
        from openai import OpenAI
    except ImportError as e:
        raise OpenAIWhisperAPIError(
            "openai package not installed. Run: pip install -e '.[ptt]'"
        ) from e

    client = OpenAI(api_key=api_key)
    with open(path, "rb") as f:
        try:
            resp = client.audio.transcriptions.create(
                model=model,
                file=f,
                response_format="text",
            )
        except Exception as e:
            msg = str(e)
            if "api_key" in msg.lower() or "401" in msg or "authentication" in msg.lower():
                raise OpenAIWhisperAPIError(
                    "Invalid OPENAI_API_KEY. Check your .env or export OPENAI_API_KEY=sk-..."
                ) from e
            if "insufficient_quota" in msg.lower() or "429" in msg:
                raise OpenAIWhisperAPIError(
                    "OpenAI API quota exceeded. Check your billing."
                ) from e
            raise OpenAIWhisperAPIError(f"Whisper API failed: {e}") from e

    if isinstance(resp, str):
        return resp.strip()
    return str(resp).strip() if resp else ""
