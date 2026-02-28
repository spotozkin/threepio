"""Echo guard: detect and remove echoed user content from assistant text before TTS."""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

OVERLAP_THRESHOLD = 0.30  # >30% overlap triggers removal


def _normalize(s: str) -> str:
    """Normalize for comparison."""
    return re.sub(r"\s+", " ", s.strip().lower())


def _longest_overlap(user_text: str, assistant_text: str) -> tuple[int, int, str]:
    """
    Find longest significant substring of user_text that appears in assistant_text.
    Returns (start_in_assistant, end_in_assistant, matched_substring) or (0, 0, "").
    """
    if not user_text or not assistant_text:
        return (0, 0, "")
    alower = assistant_text.lower()
    # Try substrings of user_text from longest to shortest (min 15 chars)
    for length in range(min(len(user_text), len(assistant_text)), 14, -1):
        for i in range(len(user_text) - length + 1):
            sub = user_text[i : i + length]
            if len(sub.strip()) < 15:
                continue
            idx = alower.find(sub.lower())
            if idx >= 0:
                return (idx, idx + length, sub)
    return (0, 0, "")


def apply_echo_guard(
    user_text: str,
    assistant_text: str,
    overlap_threshold: float = OVERLAP_THRESHOLD,
) -> str:
    """
    Remove echoed user content from assistant text. Returns cleaned text.

    - If assistant contains user prompt verbatim, remove it.
    - If >overlap_threshold of user text appears as a substring in assistant, remove that portion.
    """
    if not assistant_text or not user_text:
        return assistant_text

    # Check verbatim containment (case-insensitive)
    user_clean = user_text.strip()
    if len(user_clean) >= 10:
        idx = assistant_text.lower().find(user_clean.lower())
        if idx >= 0:
            # Do not remove if inside quotes (legitimate clarification)
            before_match = assistant_text[:idx]
            after_match = assistant_text[idx + len(user_clean) :]
            char_before = before_match[-1] if before_match else ""
            char_after = after_match[0] if after_match else ""
            if char_before in '"\'' and char_after in '"\'':
                # Quoted clarification; leave as-is
                pass
            else:
                before = before_match.rstrip()
                after = after_match.lstrip()
                result = (before + " " + after).strip() if before and after else (before or after)
                logger.warning(
                    "[echo_guard] Removed verbatim user prompt from assistant (len=%d)",
                    len(user_clean),
                )
                return result if result else assistant_text

    # Check overlap: longest user substring in assistant
    start, end, matched = _longest_overlap(user_text, assistant_text)
    if not matched:
        return assistant_text

    # Do not remove if inside quotes (legitimate clarification)
    char_before = assistant_text[start - 1] if start > 0 else ""
    char_after = assistant_text[end] if end < len(assistant_text) else ""
    if char_before in '"\'' and char_after in '"\'':
        return assistant_text

    user_len = len(user_text.strip())
    if user_len > 0 and (len(matched) / user_len) > overlap_threshold:
        before = assistant_text[:start].rstrip()
        after = assistant_text[end:].lstrip()
        result = (before + " " + after).strip() if before and after else (before or after)
        logger.warning(
            "[echo_guard] Removed echoed substring (overlap %.0f%%, len=%d)",
            100 * len(matched) / user_len,
            len(matched),
        )
        return result if result else assistant_text

    return assistant_text
