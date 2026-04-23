#!/usr/bin/env bash
# Probe audio: list devices, record 2s to /tmp/threepio_mic_test.wav (16k mono), play back. Exit nonzero on failure.
set -euo pipefail

echo "[pi_audio_probe] Playback devices (aplay -l):"
aplay -l || true
echo ""
echo "[pi_audio_probe] Capture devices (arecord -l):"
arecord -l || true
echo ""

OUT="/tmp/threepio_mic_test.wav"
DUR=2
RATE=16000
CHANS=1

echo "[pi_audio_probe] Recording ${DUR}s at ${RATE} Hz mono to $OUT ..."
if ! arecord -q -f S16_LE -r "$RATE" -c "$CHANS" -d "$DUR" "$OUT"; then
  echo "[pi_audio_probe] arecord failed" >&2
  exit 1
fi
if [[ ! -f "$OUT" ]] || [[ ! -s "$OUT" ]]; then
  echo "[pi_audio_probe] No or empty file $OUT" >&2
  exit 1
fi
echo "[pi_audio_probe] Playing back..."
if ! aplay -q "$OUT"; then
  echo "[pi_audio_probe] aplay failed" >&2
  exit 1
fi
echo "[pi_audio_probe] OK"
