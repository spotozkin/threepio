#!/usr/bin/env bash
# THREEPIO Raspberry Pi install: deps, venv, log dir, systemd, logrotate.
# Run from repo root: ./scripts/pi_install.sh (some steps need sudo)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"
DEPLOY_USER="${SUDO_USER:-$USER}"

echo "[pi_install] Installing apt dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
  python3-venv \
  python3-pip \
  ffmpeg \
  portaudio19-dev \
  alsa-utils

chmod +x scripts/*.sh systemd/threepio_wrapper.sh 2>/dev/null || true
echo "[pi_install] Creating venv at .venv..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
# Install project (pyproject.toml) and ambient deps
pip install -e .
pip install sounddevice numpy

echo "[pi_install] Creating log directory /var/log/threepio (owner ${DEPLOY_USER}:${DEPLOY_USER})..."
sudo mkdir -p /var/log/threepio
sudo chown "${DEPLOY_USER}:${DEPLOY_USER}" /var/log/threepio

echo "[pi_install] Installing systemd service..."
sudo cp -f systemd/threepio.service /etc/systemd/system/
sudo sed -i "s|/home/pi/threepio|$REPO_ROOT|g" /etc/systemd/system/threepio.service
chmod +x systemd/threepio_wrapper.sh
sudo systemctl daemon-reload

echo "[pi_install] Installing logrotate config..."
sudo cp -f systemd/logrotate_threepio /etc/logrotate.d/threepio

echo "[pi_install] Done."
echo ""
echo "--- Next steps ---"
echo "1. Edit config/pi.env: cp config/pi.env.example config/pi.env && nano config/pi.env (add API keys, device names after probe)"
echo "2. Configure I2S overlays in /boot/firmware/config.txt (see docs/PI_DEPLOYMENT.md), then: sudo reboot"
echo "3. After reboot, run: ./scripts/pi_audio_probe.sh  (note aplay -l / arecord -l; set THREEPIO_AUDIO_INPUT_DEVICE and THREEPIO_AUDIO_OUTPUT_DEVICE in config/pi.env)"
echo "4. Enable and start: sudo systemctl enable threepio && sudo systemctl start threepio"
echo "5. Check logs: tail -f /var/log/threepio/ambient.log  or  journalctl -u threepio -f"
