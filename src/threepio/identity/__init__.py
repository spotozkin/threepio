"""Speaker identity (voice recognition)."""

from threepio.identity.voice_id import (
    compute_embedding,
    cosine_similarity,
    enroll_voiceprint,
    load_voiceprints,
    match_speaker,
    record_one_utterance,
)

__all__ = [
    "compute_embedding",
    "cosine_similarity",
    "enroll_voiceprint",
    "load_voiceprints",
    "match_speaker",
    "record_one_utterance",
]
