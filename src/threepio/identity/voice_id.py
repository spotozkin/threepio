"""
Speaker identification (voiceprints). Uses resemblyzer for embeddings.
No cloud services; embeddings only, no raw audio stored after enrollment.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VOICEPRINTS_DIR = Path("data/memory/voiceprints")
DEFAULT_THRESHOLD = 0.80
# Frame duration in seconds (30 ms per frame from mic_stream)
FRAME_DURATION_SEC = 30 / 1000.0

# Module-level singleton; cold torch import can be slow
_ENCODER: Any = None


def get_encoder() -> Any:
    """Lazy-init and cache resemblyzer VoiceEncoder (CPU). Reused for all compute_embedding calls."""
    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER
    try:
        from resemblyzer import VoiceEncoder
    except ImportError as e:
        raise RuntimeError(
            "Voice ID requires resemblyzer. Install with: pip install Resemblyzer\n"
            "Note: Resemblyzer depends on PyTorch; on Raspberry Pi use: pip install torch --index-url https://download.pytorch.org/whl/cpu"
        ) from e
    encoder = VoiceEncoder(device="cpu", verbose=False)
    _ENCODER = encoder
    return _ENCODER


def _preprocess_wav(wav_path: str | Path) -> Any:
    """Load and preprocess WAV for resemblyzer (expects 16 kHz mono)."""
    try:
        from resemblyzer import preprocess_wav
    except ImportError as e:
        raise RuntimeError(
            "Voice ID requires resemblyzer. Install with: pip install Resemblyzer"
        ) from e
    return preprocess_wav(str(wav_path))


def compute_embedding(wav_path: str | Path) -> list[float]:
    """Compute speaker embedding from a WAV file (16 kHz mono). Returns 256-dim list. Uses cached encoder."""
    wav = _preprocess_wav(wav_path)
    encoder = get_encoder()
    embed = encoder.embed_utterance(wav)
    return embed.tolist()


def utterance_duration_sec(num_frames: int) -> float:
    """Duration in seconds for num_frames at 30 ms per frame."""
    return num_frames * FRAME_DURATION_SEC


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors (assume already L2-normalized for 0..1 range)."""
    if len(a) != len(b) or not a:
        return 0.0
    try:
        dot = sum(x * y for x, y in zip(a, b))
        return max(-1.0, min(1.0, float(dot)))
    except Exception:
        return 0.0


def _slug(name: str) -> str:
    """File-safe slug from display name."""
    s = re.sub(r"[^\w\s-]", "", name.strip().lower())
    return re.sub(r"[-\s]+", "_", s) or "user"


def load_voiceprints(dir_path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    """Load all voiceprints from directory. Returns dict keyed by name: {name, created_at, updated_at, threshold, embeddings}."""
    base = Path(dir_path) if dir_path is not None else VOICEPRINTS_DIR
    out: dict[str, dict[str, Any]] = {}
    if not base.exists():
        return out
    for f in base.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            name = data.get("name") or f.stem
            out[name] = {
                "name": name,
                "created_at": data.get("created_at"),
                "updated_at": data.get("updated_at"),
                "threshold": float(data.get("threshold", DEFAULT_THRESHOLD)),
                "embeddings": list(data.get("embeddings", [])),
            }
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("voiceprint load %s: %s", f, e)
    return out


def match_speaker(
    embedding: list[float],
    voiceprints: dict[str, dict[str, Any]] | None = None,
    top_k: int = 2,
) -> tuple[str | None, float, list[tuple[str, float]]]:
    """
    Find best matching speaker. Returns (best_name, best_score, top_k_list).
    best_name is None if best_score < that voiceprint's threshold (conservative).
    """
    if voiceprints is None:
        voiceprints = load_voiceprints()
    if not voiceprints or not embedding:
        return (None, 0.0, [])

    scores: list[tuple[str, float]] = []
    for name, vp in voiceprints.items():
        embs = vp.get("embeddings") or []
        if not embs:
            continue
        best = max(
            cosine_similarity(embedding, e) if isinstance(e, list) else 0.0
            for e in embs
        )
        scores.append((name, best))
    scores.sort(key=lambda x: -x[1])
    top = scores[:top_k]
    best_name, best_score = scores[0] if scores else (None, 0.0)
    threshold = DEFAULT_THRESHOLD
    if best_name and best_name in voiceprints:
        threshold = voiceprints[best_name].get("threshold", DEFAULT_THRESHOLD)
    if best_score < threshold:
        best_name = None
    return (best_name, best_score, top)


def enroll_voiceprint(
    name: str,
    embeddings: list[list[float]],
    threshold: float = DEFAULT_THRESHOLD,
    dir_path: str | Path | None = None,
) -> Path:
    """
    Save a new or updated voiceprint. Only call from --enroll-voice CLI.
    Never update automatically. embeddings: list of 256-dim vectors from compute_embedding().
    """
    if not embeddings:
        raise ValueError("At least one embedding required to enroll")
    base = Path(dir_path) if dir_path is not None else VOICEPRINTS_DIR
    base.mkdir(parents=True, exist_ok=True)
    slug = _slug(name)
    path = base / f"{slug}.json"
    now = datetime.now(timezone.utc).isoformat()
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    data: dict[str, Any] = {
        "name": name.strip(),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
        "threshold": threshold,
        "embeddings": embeddings,
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    logger.info("Enrolled voiceprint for %s (%d embeddings) at %s", name, len(embeddings), path)
    return path


def record_one_utterance(
    mic: Any,
    silence_ms: int = 700,
    max_frames: int = 300,
) -> list[bytes] | None:
    """
    Block until one utterance is captured (speech start -> speech end). Uses same VAD/energy
    logic as ambient. Returns list of frames (bytes) or None if timeout/failure.
    Caller must write to WAV and delete temp file; no raw audio stored here.
    """
    from collections import deque
    from threepio.audio.vad import (
        VAD_BYTES_PER_FRAME,
        VAD_FRAME_MS,
        detect_speech_end,
        detect_speech_start,
        energy_speech_end,
        energy_speech_start,
    )
    from threepio.audio.mic_stream import frame_rms_peak

    silence_frames = max(1, silence_ms // VAD_FRAME_MS)
    rms_recent: deque[float] = deque(maxlen=max(silence_frames + 5, 50))
    state = "IDLE"
    listen_frames: list[bytes] = []
    timeout_frames = 500  # ~15s max wait for start
    frames_read = 0

    while True:
        frame = mic.read_frame()
        if frame is None:
            return None
        frames_read += 1
        if frames_read > timeout_frames and state == "IDLE":
            return None
        rms, peak = frame_rms_peak(frame)
        rms_recent.append(rms)
        frame_ok = len(frame) == VAD_BYTES_PER_FRAME
        if state == "IDLE":
            preroll = mic.get_preroll_frames()
            vad_start = frame_ok and detect_speech_start(
                preroll + [frame], current_rms=rms, current_peak=peak, log_event=False
            )
            energy_start = energy_speech_start(rms_recent, n_frames=3)
            if vad_start or energy_start:
                state = "LISTENING"
                listen_frames = list(preroll) + [frame]
        elif state == "LISTENING":
            listen_frames.append(frame)
            if len(listen_frames) > max_frames:
                listen_frames = listen_frames[-max_frames:]
            vad_end = frame_ok and detect_speech_end(
                listen_frames, silence_ms_threshold=silence_ms, current_rms=rms, current_peak=peak, log_event=False
            )
            energy_end = energy_speech_end(rms_recent, silence_frames)
            if vad_end or energy_end:
                return listen_frames
    return None
