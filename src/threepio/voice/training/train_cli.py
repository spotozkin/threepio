"""Training CLI: validate dataset and print next steps."""

import argparse
import json
import sys
from pathlib import Path


MIN_CLIPS_RECOMMENDED = 500


def main() -> int:
    """CLI entry: validate dataset, print stats and recommendations."""
    parser = argparse.ArgumentParser(description="Train local voice model")
    parser.add_argument(
        "--metadata",
        type=Path,
        default=Path("data/voice_clean/metadata.csv"),
        help="Path to metadata.csv",
    )
    parser.add_argument(
        "--wavs-dir",
        type=Path,
        default=Path("data/voice_clean/wavs"),
        help="Directory containing wav files",
    )
    parser.add_argument(
        "--stats",
        type=Path,
        default=Path("data/voice_clean/stats.json"),
        help="Path to stats.json (optional)",
    )
    args = parser.parse_args()

    metadata_path = args.metadata.resolve()
    wavs_dir = args.wavs_dir.resolve()
    stats_path = args.stats.resolve()

    if not metadata_path.exists():
        print(f"[ERROR] Metadata file not found: {metadata_path}")
        print("Run preprocess first: python -m threepio.voice.dataset.preprocess --in data/voice_raw --out data/voice_clean")
        return 1

    if not wavs_dir.exists():
        print(f"[ERROR] Wavs directory not found: {wavs_dir}")
        return 1

    lines = metadata_path.read_text(encoding="utf-8").strip().splitlines()
    data_lines = [ln for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    clip_count = len(data_lines)

    total_duration_sec: float | None = None
    if stats_path.exists():
        try:
            stats = json.loads(stats_path.read_text(encoding="utf-8"))
            total_duration_sec = stats.get("total_duration_sec")
        except (json.JSONDecodeError, OSError):
            pass

    if total_duration_sec is None and data_lines:
        total_duration_sec = 0.0
        for ln in data_lines:
            parts = ln.split("|")
            if len(parts) >= 3:
                try:
                    total_duration_sec += float(parts[2].strip())
                except ValueError:
                    pass

    print(f"Dataset: {clip_count} clips")
    if total_duration_sec is not None:
        print(f"Total duration: {total_duration_sec:.1f} s")
    print(f"Metadata: {metadata_path}")
    print(f"Wavs: {wavs_dir}")

    if clip_count < MIN_CLIPS_RECOMMENDED:
        print(f"\n[RECOMMEND] Minimum {MIN_CLIPS_RECOMMENDED} clips recommended for first fine-tune. Current: {clip_count}")
    else:
        print(f"\n[OK] Clip count ({clip_count}) meets recommended minimum ({MIN_CLIPS_RECOMMENDED})")

    has_placeholders = any(
        len(ln.split("|")) >= 2 and ln.split("|")[1].strip() == "__TRANSCRIBE_ME__"
        for ln in data_lines
    )
    next_steps = ["- Create .venv-train and install ML deps (torch, etc.)", "- Implement training loop for Track 2", "- Export checkpoint to LOCAL_VOICE_MODEL_DIR"]
    if has_placeholders:
        next_steps.insert(0, "- Transcribe: replace __TRANSCRIBE_ME__ in metadata.csv with actual transcripts")
    print("\nNext steps:\n" + "\n".join(next_steps) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
