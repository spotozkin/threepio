# Raspberry Pi deployment (THREEPIO)

Deploy THREEPIO on **Raspberry Pi OS Lite (64-bit)** headless via SSH.

---

## 1. Flash the SD card

- Use [Raspberry Pi Imager](https://www.raspberrypi.com/software/).
- Choose **Raspberry Pi OS (64-bit)** → **Raspberry Pi OS Lite**.
- In Imager **Advanced options** (gear icon):
  - Set hostname (e.g. `threepio`).
  - **Enable SSH** (password or public key).
  - Set username/password (e.g. `pi`).
  - **Configure Wi-Fi** (SSID and password) if not using Ethernet.
  - Set locale/timezone as needed.
- Write to SD card, insert in Pi, and boot.

---

## 2. SSH and bootstrap

```bash
ssh pi@threepio.local
```

Clone the repo and run the bootstrap script (installs system packages):

```bash
git clone <REPO_URL> /home/pi/threepio
cd /home/pi/threepio
chmod +x scripts/pi_bootstrap.sh
sudo ./scripts/pi_bootstrap.sh
sudo reboot
```

After reboot, SSH in again. Bootstrap installs: git, ffmpeg, python3, python3-pip, python3-venv, build-essential, cmake, pkg-config, libatlas-base-dev, libffi-dev, libssl-dev, portaudio19-dev, libasound2-dev, htop, tmux, curl.

---

## 3. Python venv and dependencies

```bash
cd /home/pi/threepio
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .
# Optional: pip install -e ".[voice]"
```

---

## 4. Create .env

Create `/home/pi/threepio/.env` with your API keys and config. Do not commit this file.

Example:

```
PROVIDER_LLM=openai
OPENAI_API_KEY=sk-...
PROVIDER_TTS=elevenlabs
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...
```

**Audio on Pi:** Set `AUDIO_OUTPUT_MODE` to `auto`, `ffplay`, or `aplay` — not `afplay` (macOS only).

---

## 5. Test before enabling service

```bash
cd /home/pi/threepio && source .venv/bin/activate
python -m threepio --tts-test
python -m threepio --mic-test
python -m threepio --ambient
# Ctrl+C to stop
```

---

## 6. Install and enable systemd service

```bash
sudo cp /home/pi/threepio/deploy/threepio.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable threepio
sudo systemctl start threepio
```

The service runs: `/home/pi/threepio/.venv/bin/python -m threepio --ambient` with `EnvironmentFile=/home/pi/threepio/.env`.

---

## 7. Logs and control

- Follow logs: `journalctl -u threepio -f`
- Stop: `sudo systemctl stop threepio`
- Start: `sudo systemctl start threepio`
