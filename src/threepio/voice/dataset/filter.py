"""Filter voice dataset for Track 2 TTS prep."""

import argparse
import json
import re
import sys
from pathlib import Path

REASON_EMPTY = "empty_transcript"
REASON_SHORT_CHARS = "transcript_too_short"
REASON_DURATION_MIN = "duration_too_short"
REASON_DURATION_MAX = "duration_too_long"
REASON_ASR_JUNK = "asr_junk"


def is_asr_junk(transcript: str) -> bool:
    """True if transcript looks like ASR junk: repeated chars, only punctuation."""
    s = transcript.strip()
    if not s:
        return True
    # Only punctuation/whitespace
    if not re.sub(r"[\s.,;:!?'\"\-—–…\[\](){}]+", "", s):
        return True
    # 4+ repeated same char (e.g. "aaaa", "...", "eeee")
    if re.search(r"(.)\1{3,}", s):
        return True
    return False


def main() -> int:
    """CLI entry: filter metadata.csv by duration, length, and junk patterns."""
    parser = argparse.ArgumentParser(description="Filter voice dataset for TTS")
    parser.add_argument("--dataset", type=Path, required=True, help="Dataset directory")
    parser.add_argument("--min_sec", type=float, default=1.2)
    parser.add_argument("--max_sec", type=float, default=10.0)
    parser.add_argument("--min_chars", type=int, default=8)
    parser.add_argument("--out", type=Path, required=True, help="Output filtered CSV path")
    args = parser.parse_args()

    dataset_dir = args.dataset.resolve()
    metadata_path = dataset_dir / "metadata.csv"
    out_path = args.out.resolve()

    if not metadata_path.exists():
        print(f"[ERROR] Metadata not found: {metadata_path}")
        return 1

    lines = metadata_path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    if not lines:
        print("[ERROR] Empty metadata")
        return 1

    header = lines[0]
    if "|" not in header:
        print("[ERROR] Expected format: audio_path|transcript|duration_sec")
        return 1

    removed: dict[str, int] = {
        REASON_EMPTY: 0,
        REASON_SHORT_CHARS: 0,
        REASON_DURATION_MIN: 0,
        REASON_DURATION_MAX: 0,
        REASON_ASR_JUNK: 0,
    }
    kept: list[str] = []
    total = 0

    for ln in lines[1:]:
        parts = ln.split("|", 2)
        if len(parts) < 2:
            removed[REASON_EMPTY] += 1
            total += 1
            continue
        path = parts[0].strip()
        transcript = parts[1].strip()
        duration_str = parts[2].strip() if len(parts) > 2 else ""
        total += 1

        if not transcript:
            removed[REASON_EMPTY] += 1
            continue
        if len(transcript) < args.min_chars:
            removed[REASON_SHORT_CHARS] += 1
            continue
        try:
            dur = float(duration_str) if duration_str else 0.0
        except ValueError:
            dur = 0.0
        if dur < args.min_sec:
            removed[REASON_DURATION_MIN] += 1
            continue
        if dur > args.max_sec:
            removed[REASON_DURATION_MAX] += 1
            continue
        if is_asr_junk(transcript):
            removed[REASON_ASR_JUNK] += 1
            continue
        kept.append(ln)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(header + "\n" + "\n".join(kept) + "\n", encoding="utf-8")
    print(f"[INFO] Kept {len(kept)} / {total} rows -> {out_path}")

    report = {
        "total_input": total,
        "total_kept": len(kept),
        "total_removed": total - len(kept),
        "removed_by_reason": removed,
    }
    report_path = dataset_dir / "filter_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[INFO] Report: {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
