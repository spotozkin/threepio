"""Transcribe __TRANSCRIBE_ME__ clips using faster-whisper (training venv only)."""

import argparse
import json
import math
import re
import shutil
import sys
from pathlib import Path

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("[ERROR] This script requires faster-whisper. Install in .venv-train:")
    print("  pip install faster-whisper")
    sys.exit(1)

PLACEHOLDER = "__TRANSCRIBE_ME__"
WRITE_EVERY_N = 10


def clean_transcript(text: str) -> str:
    """Strip whitespace, collapse multiple spaces, remove leading/trailing quotes."""
    s = text.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.strip("'\"").strip()
    return s


def transcribe_audio(model: WhisperModel, wav_path: Path, language: str | None) -> tuple[str, float | None]:
    """Run Whisper on wav file. Returns (transcript, avg_logprob or None)."""
    segs, info = model.transcribe(str(wav_path), language=language or None)
    texts: list[str] = []
    logprobs: list[float] = []
    for seg in segs:
        t = seg.text.strip()
        if t:
            texts.append(t)
            if hasattr(seg, "avg_logprob") and seg.avg_logprob is not None:
                logprobs.append(seg.avg_logprob)
    transcript = " ".join(texts)
    avg_logprob = sum(logprobs) / len(logprobs) if logprobs else None
    return transcript, avg_logprob


def main() -> int:
    """CLI entry: transcribe placeholder rows in metadata.csv."""
    parser = argparse.ArgumentParser(description="Transcribe clips with __TRANSCRIBE_ME__")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/voice_clean"),
        help="Dataset directory (contains metadata.csv and wavs/)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="base",
        help="Whisper model size (tiny, base, small, medium, large-v2, etc.)",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="en",
        help="Language code (en, es, etc.) or 'auto'",
    )
    parser.add_argument(
        "--write-every",
        type=int,
        default=WRITE_EVERY_N,
        help="Save metadata every N transcriptions",
    )
    args = parser.parse_args()

    dataset_dir = args.dataset.resolve()
    metadata_path = dataset_dir / "metadata.csv"
    wavs_dir = dataset_dir / "wavs"

    if not metadata_path.exists():
        print(f"[ERROR] Metadata not found: {metadata_path}")
        return 1

    if not wavs_dir.exists():
        print(f"[ERROR] Wavs directory not found: {wavs_dir}")
        return 1

    # Backup
    bak_path = dataset_dir / "metadata.csv.bak"
    if not bak_path.exists():
        shutil.copy2(metadata_path, bak_path)
        print(f"[INFO] Backup: {bak_path}")

    lines = metadata_path.read_text(encoding="utf-8").rstrip("\n").split("\n")
    if not lines:
        print("[ERROR] Empty metadata")
        return 1

    header = lines[0]
    data_lines = lines[1:]

    # Parse rows: path|text|duration
    rows: list[list[str]] = []
    for ln in data_lines:
        parts = ln.split("|", 2)
        if len(parts) < 2:
            rows.append([ln, "", ""])
        elif len(parts) == 2:
            rows.append([parts[0].strip(), parts[1].strip(), ""])
        else:
            rows.append([p.strip() for p in parts])

    total_clips = len(rows)
    to_transcribe = [(i, r) for i, r in enumerate(rows) if r[1] == PLACEHOLDER]
    skipped = total_clips - len(to_transcribe)

    if not to_transcribe:
        print("[INFO] No __TRANSCRIBE_ME__ rows; nothing to do")
        _write_report(dataset_dir, total_clips, 0, skipped, None, args.model)
        return 0

    print(f"[INFO] Loading model: {args.model}")
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    lang = None if args.language.lower() == "auto" else args.language

    transcribed = 0
    logprobs: list[float] = []

    for idx, (row_idx, row) in enumerate(to_transcribe):
        rel_path = row[0]
        wav_path = (dataset_dir / rel_path).resolve()
        if not wav_path.exists():
            print(f"[WARN] Missing: {wav_path}")
            rows[row_idx][1] = ""
            continue
        print(f"[{idx + 1}/{len(to_transcribe)}] {rel_path}")
        try:
            text, avg_lp = transcribe_audio(model, wav_path, lang)
            text = clean_transcript(text)
            rows[row_idx][1] = text if text else "[inaudible]"
            transcribed += 1
            if avg_lp is not None:
                logprobs.append(avg_lp)
        except Exception as e:
            print(f"[ERROR] {rel_path}: {e}")
            rows[row_idx][1] = "[error]"

        if (idx + 1) % args.write_every == 0:
            _write_metadata(metadata_path, header, rows)
            print(f"[INFO] Saved ({idx + 1} done)")

    _write_metadata(metadata_path, header, rows)
    avg_conf = _avg_confidence(logprobs)
    _write_report(dataset_dir, total_clips, transcribed, skipped, avg_conf, args.model)
    print(f"[INFO] Done. Transcribed: {transcribed}, Skipped: {skipped}")
    return 0


def _write_metadata(metadata_path: Path, header: str, rows: list[list[str]]) -> None:
    """Write metadata.csv."""
    out_lines = [header]
    for r in rows:
        if len(r) >= 3:
            out_lines.append(f"{r[0]}|{r[1]}|{r[2]}")
        elif len(r) == 2:
            out_lines.append(f"{r[0]}|{r[1]}|")
        else:
            out_lines.append(r[0])
    metadata_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def _avg_confidence(logprobs: list[float]) -> float | None:
    """Convert avg_logprob to 0–1 confidence. Higher logprob = more confident."""
    if not logprobs:
        return None
    # avg_logprob typically in [-1, 0]; exp maps to (0.37, 1]
    probs = [math.exp(lp) for lp in logprobs]
    return round(sum(probs) / len(probs), 4)


def _write_report(
    dataset_dir: Path,
    total_clips: int,
    transcribed: int,
    skipped: int,
    avg_confidence: float | None,
    model_name: str,
) -> None:
    """Write transcribe_report.json."""
    report = {
        "total_clips": total_clips,
        "transcribed": transcribed,
        "skipped": skipped,
        "avg_confidence": avg_confidence,
        "model_name": model_name,
    }
    path = dataset_dir / "transcribe_report.json"
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"[INFO] Report: {path}")


if __name__ == "__main__":
    sys.exit(main())
