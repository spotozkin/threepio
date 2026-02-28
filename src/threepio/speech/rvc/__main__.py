"""CLI for RVC conversion self-test.

Run: ENABLE_RVC=1 RVC_MODEL_PATH=models/rvc/c3po/model.pth \\
  python -m threepio.speech.rvc --in input.wav --out /tmp/rvc_test.wav

Uses env: ENABLE_RVC, RVC_MODEL_PATH, RVC_INDEX_PATH, RVC_BACKEND (cli|python), etc.
Default RVC_BACKEND=cli uses tools/rvc_infer.py with local RVC repo in tools/rvc/.
"""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="RVC voice conversion (self-test)")
    parser.add_argument("--in", dest="input_path", required=True, help="Input WAV path")
    parser.add_argument("--out", dest="output_path", required=True, help="Output WAV path")
    args = parser.parse_args()

    in_path = Path(args.input_path).resolve()
    out_path = Path(args.output_path).resolve()

    if not in_path.exists():
        print(f"[ERROR] Input not found: {in_path}", file=sys.stderr)
        return 1

    from threepio.speech.rvc.rvc_converter import get_rvc_converter_or_none

    converter = get_rvc_converter_or_none()
    if converter is None:
        print(
            "[ERROR] RVC not available. Set ENABLE_RVC=1, RVC_MODEL_PATH. "
            "For CLI backend, ensure tools/rvc/ exists (see README).",
            file=sys.stderr,
        )
        return 1

    try:
        audio_bytes = converter.convert_wav_bytes(in_path.read_bytes())
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(audio_bytes)
        print(f"[OK] Wrote {len(audio_bytes)} bytes to {out_path}")
        return 0
    except Exception as e:
        print(f"[ERROR] Conversion failed: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
