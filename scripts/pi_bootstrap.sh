#!/usr/bin/env bash
# Bootstrap for Raspberry Pi OS Lite (64-bit) for THREEPIO. Run: sudo ./scripts/pi_bootstrap.sh
set -euo pipefail

echo "[pi_bootstrap] Updating package lists..."
apt-get update -qq

echo "[pi_bootstrap] Upgrading existing packages..."
apt-get upgrade -y -qq

echo "[pi_bootstrap] Installing THREEPIO dependencies..."
apt-get install -y -qq \
  git \
  ffmpeg \
  python3 \
  python3-pip \
  python3-venv \
  build-essential \
  cmake \
  pkg-config \
  libatlas-base-dev \
  libffi-dev \
  libssl-dev \
  portaudio19-dev \
  libasound2-dev \
  htop \
  tmux \
  curl

echo "[pi_bootstrap] Done. Reboot recommended: sudo reboot"
