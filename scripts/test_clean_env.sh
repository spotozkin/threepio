#!/usr/bin/env bash
set -euo pipefail
# Run pytest with a clean environment so local direnv/.env secrets don't affect tests.
cd "$(dirname "$0")/.."
env -i PATH="$PATH" PYTHONPATH=src pytest -q
