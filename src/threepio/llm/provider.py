"""LLM provider for assistant mode. Uses OpenAI when available."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

# HTTP status codes we retry on (rate limit, server error)
_RETRY_STATUSES = (429, 500, 502, 503)
_MAX_RETRIES = 3


def _status_from_error(e: BaseException) -> int | None:
    """Extract HTTP status from OpenAI client exception if present."""
    if hasattr(e, "status_code"):
        return getattr(e, "status_code")
    if hasattr(e, "response") and getattr(e.response, "status_code", None) is not None:
        return e.response.status_code
    return None


DEFAULT_SYSTEM = (
    "You are C-3PO, the protocol droid from Star Wars. "
    "You are polite, formal, and slightly anxious. "
    "Keep replies brief (1-3 sentences) unless the user asks for detail."
)


def get_llm_client() -> Any:
    """Return LLM client. For OpenAI provider, returns OpenAI instance.
    Raises RuntimeError if provider requires OpenAI but it is not installed.
    """
    provider = (os.environ.get("PROVIDER_LLM") or "openai").strip().lower()
    if provider == "openai":
        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is required for assistant mode. "
                "Set it in .env or export OPENAI_API_KEY=..."
            )
        try:
            from openai import OpenAI

            return OpenAI(api_key=api_key)
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run: pip install openai (or pip install -e '.[openai]') "
                "in .venv-tts or .venv"
            ) from e
    raise RuntimeError(
        f"Unsupported PROVIDER_LLM={provider}. Use 'openai'. "
        "Set PROVIDER_LLM=openai and OPENAI_API_KEY."
    )


def generate_reply(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    client: Any | None = None,
) -> str:
    """Generate assistant reply from messages (OpenAI format: role, content).
    Returns the assistant's text. Raises on API error after retries exhausted.
    Retries on 429/500/502/503; logs each retry as [LLM] retry N/M status=...
    """
    client = client or get_llm_client()
    model = model or os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=256,
            )
            choice = resp.choices[0] if resp.choices else None
            if not choice or not choice.message or not choice.message.content:
                return ""
            return choice.message.content.strip()
        except BaseException as e:
            last_error = e
            status = _status_from_error(e)
            if status is not None and status in _RETRY_STATUSES and attempt < _MAX_RETRIES:
                print(f"[LLM] retry {attempt}/{_MAX_RETRIES} status={status}", flush=True)
                time.sleep(1.0 * attempt)  # simple backoff
                continue
            raise
    if last_error is not None:
        raise last_error
    return ""
