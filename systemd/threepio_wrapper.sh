#!/usr/bin/env bash
# Wrapper for systemd: load env, run net wait + chime, then start ambient. Run with WorkingDirectory=repo root.
set -euo pipefail

# Repo root: when run by systemd, WorkingDirectory is set to /home/pi/threepio (or install path)
ROOT="${THREEPIO_ROOT:-$(pwd)}"
cd "$ROOT"

ENV_FILE="${ENV_FILE:-$ROOT/config/pi.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

"$ROOT/scripts/pi_net_wait_and_chime.sh" "$ROOT" || true

exec "$ROOT/.venv/bin/python" -m threepio --ambient
