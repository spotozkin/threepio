"""Speech shaping: SSML-style breaks for cadence. Produces display_text and speech_text."""

from __future__ import annotations

import re

# Break tags (ElevenLabs may or may not support SSML; keep module either way)
BREAK_SENTENCE = '<break time="320ms" />'
BREAK_CLAUSE = '<break time="180ms" />'
BREAK_EMDASH = '<break time="160ms" />'

MAX_BREAKS = 18  # Cap to avoid spam

# Patterns that should not be followed by a break (abbreviations, decimals)
DECIMAL_OR_NUMBER_RE = re.compile(r"^\s*[\d.]")
# Abbreviation: letter.letter (e.g. U.S., U.K.)
ABBREVIATION_REST_RE = re.compile(r"^\s*[A-Za-z]\.")


def _would_break_number(pos: int, text: str) -> bool:
    """True if inserting a break at pos would split a number (e.g. 3.14, 42)."""
    rest = text[pos:].lstrip()
    return bool(DECIMAL_OR_NUMBER_RE.match(rest))


def _would_break_abbreviation(pos: int, text: str) -> bool:
    """True if inserting a break at pos would split an abbreviation (e.g. U.S.)."""
    rest = text[pos:].lstrip()
    return bool(ABBREVIATION_REST_RE.match(rest))


def shape_for_speech(text: str, max_breaks: int = MAX_BREAKS) -> tuple[str, str]:
    """
    Add subtle breaks for cadence. Returns (display_text, speech_text).

    - display_text: unchanged, for print/log
    - speech_text: with SSML breaks, for TTS (ElevenLabs may pass through or interpret)

    Rules:
    - After . ? ! -> 320ms break
    - After , ; : -> 180ms break
    - After — -> 160ms break
    - Skip inside numbers, abbreviations (U.S.), decimals
    - Cap total breaks at max_breaks (default 18)
    """
    if not text or not text.strip():
        return text, text

    display_text = text.strip()
    parts: list[tuple[int, int, str]] = []  # (end_pos, priority, tag); higher priority wins

    def _should_skip(pos: int) -> bool:
        return _would_break_number(pos, display_text) or _would_break_abbreviation(pos, display_text)

    # Sentence-ending . ? !
    for m in re.finditer(r"[.?!]\s*", display_text):
        if not _should_skip(m.end()):
            parts.append((m.end(), 3, BREAK_SENTENCE))

    # Commas, semicolons, colons
    for m in re.finditer(r"[,;:]\s*", display_text):
        if not _should_skip(m.end()):
            parts.append((m.end(), 2, BREAK_CLAUSE))

    # Em-dash
    for m in re.finditer(r"—", display_text):
        if not _should_skip(m.end()):
            parts.append((m.end(), 1, BREAK_EMDASH))

    # Dedupe by position: keep highest priority per position (sentence > clause > emdash)
    by_pos: dict[int, tuple[int, str]] = {}
    for pos, prio, tag in parts:
        if pos not in by_pos or prio > by_pos[pos][0]:
            by_pos[pos] = (prio, tag)

    # Sort by position descending, take first max_breaks
    sorted_inserts = sorted(
        ((pos, tag) for pos, (_, tag) in by_pos.items()),
        key=lambda x: -x[0],
    )[:max_breaks]

    speech_text = display_text
    for pos, tag in sorted_inserts:
        tail = speech_text[pos:].lstrip()
        speech_text = speech_text[:pos] + " " + tag + " " + tail

    return display_text, speech_text.strip()


if __name__ == "__main__":
    # Quick before/after for validation
    examples = [
        "Oh my. I appear to be fully operational.",
        "The value is 3.14, approximately.",
        "U.S. policy remains unchanged.",
        "First point; second point: and the conclusion.",
    ]
    for t in examples:
        disp, speech = shape_for_speech(t)
        print("display:", repr(disp))
        print("speech: ", repr(speech))
        print()
