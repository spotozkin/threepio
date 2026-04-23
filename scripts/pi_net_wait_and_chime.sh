#!/usr/bin/env bash
# Wait for internet (DNS + optional ping) with timeout; on success play chime.wav with aplay. Return 0 on success, nonzero on failure.
set -euo pipefail

TIMEOUT="${THREEPIO_NET_WAIT_TIMEOUT:-30}"
REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
CHIME=""
for p in "$REPO_ROOT/config/chime.wav" "$REPO_ROOT/data/chime.wav"; do
  if [[ -f "$p" ]]; then
    CHIME="$p"
    break
  fi
done

echo "[pi_net_wait] Waiting up to ${TIMEOUT}s for internet..."
DEADLINE=$(($(date +%s) + ${TIMEOUT:-30}))
while [[ $(date +%s) -lt $DEADLINE ]]; do
  if getent hosts api.openai.com >/dev/null 2>&1; then
    if command -v ping >/dev/null 2>&1; then
      if ping -c 1 -W 2 8.8.8.8 >/dev/null 2>&1; then
        echo "[pi_net_wait] Online (DNS + ping OK)"
        if [[ -n "$CHIME" ]]; then
          echo "[pi_net_wait] Playing chime: $CHIME"
          aplay -q "$CHIME" || true
        else
          echo "[pi_net_wait] No chime file (config/chime.wav or data/chime.wav)"
        fi
        exit 0
      fi
    else
      echo "[pi_net_wait] Online (DNS OK)"
      if [[ -n "$CHIME" ]]; then
        aplay -q "$CHIME" || true
      fi
      exit 0
    fi
  fi
  sleep 2
done
echo "[pi_net_wait] Timeout (no internet)" >&2
exit 1
