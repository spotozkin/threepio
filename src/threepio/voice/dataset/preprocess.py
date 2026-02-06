"""Preprocess raw voice recordings into clean WAV dataset for Track 2 TTS."""

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple

try:
    import numpy as np
    import soundfile as sf
except ImportError as e:
    print("[ERROR] This script requires numpy and soundfile. Install in .venv-train:")
    print("  pip install numpy soundfile")
    sys.exit(1)


class Segment(NamedTuple):
    """Start and end sample indices (inclusive)."""

    start: int
    end: int


def resample_linear(y: np.ndarray, sr_old: int, sr_new: int) -> np.ndarray:
    """Resample via linear interpolation. No external deps."""
    if sr_old == sr_new:
        return y.astype(np.float64, copy=True)
    duration_sec = len(y) / sr_old
    n_out = int(round(duration_sec * sr_new))
    if n_out <= 0:
        return np.array([], dtype=np.float64)
    x_old = np.arange(len(y), dtype=np.float64)
    x_new = np.linspace(0, len(y) - 1, n_out, dtype=np.float64)
    return np.interp(x_new, x_old, y.astype(np.float64))


def stereo_to_mono(y: np.ndarray) -> np.ndarray:
    """Convert stereo to mono by averaging channels."""
    if y.ndim == 1:
        return y.astype(np.float64)
    return np.mean(y, axis=1).astype(np.float64)


def load_and_prepare(path: Path, sr_target: int) -> tuple[np.ndarray, int]:
    """Load WAV, convert to mono float64, resample to sr_target."""
    data, sr = sf.read(path, dtype="float64")
    y = stereo_to_mono(data)
    if sr != sr_target:
        y = resample_linear(y, sr, sr_target)
    return y, sr_target


def compute_rms_frames(
    y: np.ndarray, sr: int, win_sec: float = 0.025, hop_sec: float = 0.010
) -> np.ndarray:
    """Compute short-time RMS per frame. Returns RMS values (linear)."""
    win_len = int(round(win_sec * sr))
    hop_len = int(round(hop_sec * sr))
    n_frames = max(0, (len(y) - win_len) // hop_len + 1)
    rms = np.zeros(n_frames, dtype=np.float64)
    eps = 1e-12
    for i in range(n_frames):
        start = i * hop_len
        chunk = y[start : start + win_len]
        if len(chunk) < win_len:
            chunk = np.pad(chunk, (0, win_len - len(chunk)))
        rms[i] = np.sqrt(np.mean(chunk**2) + eps)
    return rms


def rms_to_dbfs(rms: np.ndarray) -> np.ndarray:
    """Convert linear RMS to dBFS. Clamp to avoid -inf."""
    eps = 1e-12
    return 20 * np.log10(np.maximum(rms, eps))


def frames_to_segments(
    speech_mask: np.ndarray, hop_len: int, win_len: int, pad_samples: int, total_samples: int
) -> list[Segment]:
    """Merge speech frames into contiguous segments, add padding."""
    segments: list[Segment] = []
    in_segment = False
    seg_start = 0

    for i, is_speech in enumerate(speech_mask):
        if is_speech and not in_segment:
            in_segment = True
            seg_start = i
        elif not is_speech and in_segment:
            in_segment = False
            # Convert frame indices to sample indices
            start_sample = max(0, seg_start * hop_len - pad_samples)
            end_sample = min(total_samples, i * hop_len + win_len + pad_samples)
            segments.append(Segment(start=start_sample, end=end_sample))
    if in_segment:
        start_sample = max(0, seg_start * hop_len - pad_samples)
        end_sample = min(total_samples, len(speech_mask) * hop_len + win_len + pad_samples)
        segments.append(Segment(start=start_sample, end=end_sample))

    return segments


def split_long_segment(
    seg: Segment,
    y: np.ndarray,
    min_sec: float,
    target_min_sec: float,
    target_max_sec: float,
    hard_max_sec: float,
    sr: int,
) -> list[Segment]:
    """Split segment > hard_max_sec into chunks in [target_min_sec, target_max_sec]."""
    duration = (seg.end - seg.start) / sr
    if duration <= hard_max_sec:
        return [seg]

    chunk_samples = int(target_max_sec * sr)
    sub_segments: list[Segment] = []
    pos = seg.start

    while pos < seg.end:
        end_pos = min(pos + chunk_samples, seg.end)
        sub_dur = (end_pos - pos) / sr
        if sub_dur >= min_sec:
            sub_segments.append(Segment(start=pos, end=end_pos))
        pos = end_pos

    if sub_segments:
        last = sub_segments[-1]
        last_dur = (last.end - last.start) / sr
        if last_dur < target_min_sec and len(sub_segments) > 1:
            prev = sub_segments[-2]
            merged = Segment(prev.start, last.end)
            merged_dur = (merged.end - merged.start) / sr
            if merged_dur <= target_max_sec:
                sub_segments = sub_segments[:-2] + [merged]
            else:
                sub_segments = sub_segments[:-1]

    return sub_segments


def extract_clips(
    y: np.ndarray,
    sr: int,
    silence_db: float,
    min_sec: float,
    target_min_sec: float,
    target_max_sec: float,
    hard_max_sec: float,
    pad_ms: float,
) -> list[np.ndarray]:
    """Extract speech clips via silence splitting."""
    win_sec, hop_sec = 0.025, 0.010
    win_len = int(round(win_sec * sr))
    hop_len = int(round(hop_sec * sr))
    pad_samples = int(round(pad_ms / 1000 * sr))

    rms = compute_rms_frames(y, sr, win_sec, hop_sec)
    dbfs = rms_to_dbfs(rms)
    speech_mask = dbfs > silence_db

    raw_segments = frames_to_segments(
        speech_mask, hop_len, win_len, pad_samples, len(y)
    )

    all_segments: list[Segment] = []
    for seg in raw_segments:
        dur = (seg.end - seg.start) / sr
        if dur < min_sec:
            continue
        if dur > hard_max_sec:
            split = split_long_segment(
                seg, y, min_sec, target_min_sec, target_max_sec, hard_max_sec, sr
            )
            all_segments.extend(split)
        else:
            all_segments.append(seg)

    clips = [y[seg.start : seg.end] for seg in all_segments]
    return clips


def main() -> int:
    """CLI entry: preprocess raw WAVs into clips + metadata."""
    parser = argparse.ArgumentParser(
        description="Preprocess raw voice recordings into training dataset"
    )
    parser.add_argument("--in", dest="input_dir", type=Path, required=True)
    parser.add_argument("--out", dest="output_dir", type=Path, required=True)
    parser.add_argument("--sr", type=int, default=22050)
    parser.add_argument("--min_sec", type=float, default=1.0)
    parser.add_argument("--target_min_sec", type=float, default=2.0)
    parser.add_argument("--target_max_sec", type=float, default=10.0)
    parser.add_argument("--hard_max_sec", type=float, default=12.0)
    parser.add_argument("--silence_db", type=float, default=-40.0)
    parser.add_argument("--pad_ms", type=float, default=120.0)
    parser.add_argument("--dry_run", action="store_true")
    args = parser.parse_args()

    input_dir = args.input_dir.resolve()
    output_dir = args.output_dir.resolve()
    wavs_dir = output_dir / "wavs"

    if not input_dir.exists():
        print(f"[ERROR] Input directory does not exist: {input_dir}")
        return 1

    raw_files = sorted(input_dir.glob("*.wav"))
    if not raw_files:
        print(f"[ERROR] No WAV files in {input_dir}")
        return 1

    print(f"[INFO] Found {len(raw_files)} WAV file(s)")
    print(f"[INFO] Output: {output_dir}")
    print(f"[INFO] Target SR: {args.sr}, min_sec: {args.min_sec}")
    if args.dry_run:
        print("[INFO] DRY RUN - no files written")

    all_clips: list[np.ndarray] = []
    for path in raw_files:
        print(f"[INFO] Processing: {path.name}")
        try:
            y, sr = load_and_prepare(path, args.sr)
            clips = extract_clips(
                y,
                sr,
                args.silence_db,
                args.min_sec,
                args.target_min_sec,
                args.target_max_sec,
                args.hard_max_sec,
                args.pad_ms,
            )
            all_clips.extend(clips)
            print(f"  -> {len(clips)} clips")
        except Exception as e:
            print(f"[ERROR] Failed to process {path}: {e}")
            return 1

    if not all_clips:
        print("[WARN] No clips extracted. Adjust --silence_db or --min_sec")
        return 0 if args.dry_run else 0

    durations = [len(c) / args.sr for c in all_clips]
    total_duration = sum(durations)
    stats = {
        "total_raw_files": len(raw_files),
        "total_clips": len(all_clips),
        "total_duration_sec": round(total_duration, 2),
        "avg_clip_sec": round(total_duration / len(all_clips), 2),
        "min_clip_sec": round(min(durations), 2),
        "max_clip_sec": round(max(durations), 2),
    }

    print(f"[INFO] Total: {len(all_clips)} clips, {total_duration:.1f}s")

    if not args.dry_run:
        wavs_dir.mkdir(parents=True, exist_ok=True)
        metadata_lines = ["audio_path|transcript|duration_sec"]
        for i, (clip, dur) in enumerate(zip(all_clips, durations), start=1):
            name = f"{i:06d}.wav"
            out_path = wavs_dir / name
            clip_int16 = (np.clip(clip, -1.0, 1.0) * 32767).astype(np.int16)
            sf.write(out_path, clip_int16, args.sr, subtype="PCM_16")
            rel_path = f"wavs/{name}"
            metadata_lines.append(f"{rel_path}|__TRANSCRIBE_ME__|{dur:.2f}")
        (output_dir / "metadata.csv").write_text("\n".join(metadata_lines), encoding="utf-8")
        (output_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
        print(f"[INFO] Wrote {len(all_clips)} clips, metadata.csv, stats.json")

    return 0


if __name__ == "__main__":
    sys.exit(main())
