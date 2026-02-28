"""Smoke test for ElevenLabs TTS.

Usage:
  python -m threepio.speech.tts.elevenlabs_test --text "Hello there" --out /tmp/elevenlabs.wav

Requires: ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID in env.
"""

from __future__ import annotations

import argparse
import sys

from threepio.speech.tts.elevenlabs_provider import (
    ElevenLabsAPIError,
    ElevenLabsConfigError,
    ElevenLabsConfig,
    ElevenLabsTTS,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="ElevenLabs TTS smoke test")
    parser.add_argument("--text", default="Hello there", help="Text to synthesize")
    parser.add_argument("--out", default="/tmp/elevenlabs.wav", help="Output WAV path")
    args = parser.parse_args()

    try:
        config = ElevenLabsConfig.from_env()
    except ElevenLabsConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 1

    tts = ElevenLabsTTS(
        api_key=config.api_key,
        voice_id=config.voice_id,
        model_id=config.model_id,
        output_format=config.output_format,
        use_streaming=config.use_streaming,
        stability=config.stability,
        similarity_boost=config.similarity_boost,
        style=config.style,
        use_speaker_boost=config.use_speaker_boost,
        speed=config.speed,
        speaker=None,
    )
    try:
        written = tts.synthesize_to_file(args.text, args.out)
        print(f"Wrote: {written}")
        return 0
    except ElevenLabsAPIError as e:
        print(f"API error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
