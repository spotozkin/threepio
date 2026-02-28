"""Retrieval/soundboard TTS: pick best-matching clip from processed dataset."""

import logging
import re
from pathlib import Path

from threepio.speech.tts.base import BaseTTS

logger = logging.getLogger(__name__)

RETRIEVAL_CONFIDENCE_THRESHOLD = 0.35
FALLBACK_PHRASES = [
    "I beg your pardon?",
    "I don't understand.",
    "Could you repeat that, please?",
]


def _normalize(text: str) -> str:
    """Lowercase, strip, remove punctuation."""
    t = text.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    return t


def _tokenize(text: str) -> set[str]:
    """Tokenize into word set."""
    return set(_normalize(text).split())


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity of two sets."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _score_match(query_tokens: set[str], transcript_tokens: set[str]) -> float:
    """Score how well transcript matches query. Higher = better."""
    return _jaccard(query_tokens, transcript_tokens)


class RetrievalTTS(BaseTTS):
    """TTS that picks the best-matching pre-recorded clip from a dataset."""

    def __init__(self, dataset_dir: str | Path) -> None:
        self._dataset_dir = Path(dataset_dir).resolve()
        self._clips: list[tuple[str, str, float]] = []  # (rel_path, transcript, duration)
        self._load_dataset()

    def _load_dataset(self) -> None:
        """Load metadata.csv and wavs paths."""
        meta_path = self._dataset_dir / "metadata.csv"
        if not meta_path.exists():
            logger.warning("[RetrievalTTS] metadata.csv not found at %s", meta_path)
            return
        lines = meta_path.read_text(encoding="utf-8").strip().splitlines()
        start = 0
        if lines and "audio_path" in lines[0].lower() and "|" in lines[0]:
            start = 1
        for line in lines[start:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split("|", 2)
            if len(parts) < 2:
                continue
            rel_path = parts[0].strip()
            transcript = parts[1].strip() if len(parts) > 1 else ""
            duration = float(parts[2].strip()) if len(parts) > 2 else 0.0
            wav_path = self._dataset_dir / rel_path
            if wav_path.exists():
                self._clips.append((rel_path, transcript, duration))
            else:
                logger.debug("[RetrievalTTS] Skipping missing wav: %s", wav_path)
        logger.info("[RetrievalTTS] Loaded %d clips from %s", len(self._clips), self._dataset_dir)

    def _best_match(self, text: str) -> tuple[str, str, float] | None:
        """Return (rel_path, transcript, duration) for best match, or None."""
        result = self._best_match_with_score(text)
        return (result[:3]) if result else None

    def _best_match_with_score(self, text: str) -> tuple[str, str, float, float] | None:
        """Return (rel_path, transcript, duration, score) for best match, or None."""
        if not self._clips:
            return None
        query_tokens = _tokenize(text)
        if not query_tokens:
            rel_path, transcript, duration = self._clips[0]
            return (rel_path, transcript, duration, 1.0)
        best: tuple[str, str, float] | None = None
        best_score = -1.0
        for rel_path, transcript, duration in self._clips:
            trans_tokens = _tokenize(transcript)
            score = _score_match(query_tokens, trans_tokens)
            if score > best_score:
                best_score = score
                best = (rel_path, transcript, duration)
        if best is None:
            return None
        return (*best, best_score)

    def get_reply(self, user_text: str) -> str:
        """
        Return the transcript to use as response (retrieval-first).
        If match score >= threshold: return matched transcript.
        Else: return best fallback clip transcript or first fallback phrase.
        """
        if not self._clips:
            return FALLBACK_PHRASES[0]
        match = self._best_match_with_score(user_text)
        if match:
            rel_path, transcript, _duration, score = match
            if score >= RETRIEVAL_CONFIDENCE_THRESHOLD:
                logger.info("[RetrievalTTS] match: %r -> %s (score=%.3f)", transcript, rel_path, score)
                return transcript
        for phrase in FALLBACK_PHRASES:
            fb_match = self._best_match_with_score(phrase)
            if fb_match:
                _path, fb_transcript, _dur, fb_score = fb_match
                if fb_score >= RETRIEVAL_CONFIDENCE_THRESHOLD:
                    logger.info(
                        "[RetrievalTTS] fallback: %r (score=%.3f)",
                        fb_transcript,
                        fb_score,
                    )
                    return fb_transcript
        logger.info("[RetrievalTTS] no clip match; using fallback text")
        return FALLBACK_PHRASES[0]

    def synthesize(self, text: str) -> bytes:
        """Return WAV bytes of best-matching clip. Raises if no clips or no match."""
        match = self._best_match(text)
        if not match:
            raise RuntimeError("[RetrievalTTS] No clips in dataset or no match.")
        rel_path, _transcript, _duration = match
        wav_path = self._dataset_dir / rel_path
        return wav_path.read_bytes()

    def speak(self, text: str) -> None:
        """Find best-matching clip and output (print for now; play later)."""
        match = self._best_match(text)
        if not match:
            logger.warning("[RetrievalTTS] No clips; falling back to print")
            print(f"[TTS] {text} (no dataset)")
            return
        rel_path, transcript, _duration = match
        wav_path = self._dataset_dir / rel_path
        logger.info("[RetrievalTTS] match: %r -> %s", transcript, rel_path)
        print(f"[TTS] {transcript} (retrieval: {rel_path})")
