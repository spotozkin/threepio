# THREEPIO Raspberry Pi 5 Deployment

Production deployment for Pi 5 with I2S audio (MAX98357A DAC + INMP441 mic). Assumes deploy path `/home/pi/threepio`, venv at `/home/pi/threepio/.venv`, Pi OS Bookworm (config in `/boot/firmware/config.txt`). Default `BARGE_IN_MODE=assisted`: no STT during playback; interrupt via button/GPIO later.

---

## Checklist (do these on the Pi in order)

1. **Clone/copy repo** to `/home/pi/threepio`.
2. **Configure I2S**: edit `/boot/firmware/config.txt` (add `dtparam=i2s=on`, overlay for your HAT/card), then **reboot**.
3. **Run install**: `cd /home/pi/threepio && chmod +x scripts/*.sh systemd/threepio_wrapper.sh && ./scripts/pi_install.sh`
4. **Probe audio**: `./scripts/pi_audio_probe.sh` — note card/device from `aplay -l` and `arecord -l`.
5. **Configure env**: `cp config/pi.env.example config/pi.env && nano config/pi.env` — set API keys and `THREEPIO_AUDIO_INPUT_DEVICE` / `THREEPIO_AUDIO_OUTPUT_DEVICE` from step 4.
6. **(Optional)** Add startup chime: place `config/chime.wav` or `data/chime.wav`.
7. **Enable and start**: `sudo systemctl enable threepio && sudo systemctl start threepio`
8. **Check logs**: `tail -f /var/log/threepio/ambient.log` or `journalctl -u threepio -f`
9. **Stop when needed**: `sudo systemctl stop threepio` (graceful SIGTERM); then e.g. `sudo shutdown -h now`

---

## 1. Hardware: MAX98357A + INMP441 (I2S)

### Wiring (typical)

| Pi 5 GPIO  | MAX98357A (DAC) | INMP441 (mic) |
|-----------|-----------------|---------------|
| 3.3V      | VDD             | VDD           |
| GND       | GND             | GND           |
| GPIO 18   | BCLK            | BCLK          |
| GPIO 19   | LRCLK           | LRCLK         |
| GPIO 21   | (none)          | DOUT (data)   |
| GPIO 20   | DIN (data)      | (none)        |

- MAX98357A: I2S DAC for speaker/headphone out.
- INMP441: I2S PDM mic; data to Pi GPIO 21 (e.g. PCM_DIN on Pi).

### Enable I2S and overlays (Pi OS Bookworm)

Edit `/boot/firmware/config.txt` (sudo):

```bash
sudo nano /boot/firmware/config.txt
```

Add or uncomment:

```ini
# I2S
dtparam=i2s=on
dtoverlay=i2s-mmap

# MAX98357A (DAC) - optional, some images use googlevoicehat or similar
dtoverlay=googlevoicehat-soundcard
# Or generic I2S DAC, e.g.:
# dtoverlay=hifiberry-dac
```

For INMP441 (and many HATs) you may need a dedicated overlay or a device tree that exposes both. Example for a single “voicehat” style card that provides both:

```ini
dtoverlay=googlevoicehat-soundcard
```

Reboot after changes:

```bash
sudo reboot
```

---

## 2. Install THREEPIO

From the repo root (e.g. `/home/pi/threepio`):

```bash
cd /home/pi/threepio
chmod +x scripts/*.sh systemd/threepio_wrapper.sh
./scripts/pi_install.sh
```

This installs:

- apt: `python3-venv`, `python3-pip`, `ffmpeg`, `portaudio19-dev`, `alsa-utils`, `libasound2-dev`
- venv at `.venv` and pip installs the project + `sounddevice`, `numpy`
- `/var/log/threepio` (owner `pi:pi`)
- systemd unit `threepio.service` and logrotate config

---

## 3. Audio probe

After reboot (so I2S is active), verify devices and record/playback:

```bash
cd /home/pi/threepio
./scripts/pi_audio_probe.sh
```

- Prints `aplay -l` and `arecord -l`.
- Records 2 s at 16 kHz mono to `/tmp/threepio_mic_test.wav`, then plays it back.
- Exits nonzero on failure.

Note the **card/device** names or indices for the next step (e.g. `card 1: seeed2micvoicec`).

---

## 4. Environment file

Copy the example and edit:

```bash
cp config/pi.env.example config/pi.env
nano config/pi.env
```

Set at least:

- `OPENAI_API_KEY=sk-...`
- `ELEVENLABS_API_KEY=...` (if using ElevenLabs TTS)
- `THREEPIO_AUDIO_INPUT_DEVICE` – e.g. device index `1` or substring of device name from `arecord -l`
- `THREEPIO_AUDIO_OUTPUT_DEVICE` – leave blank for default, or ALSA device (e.g. `plughw:1,0`) if aplay needs `-D`

Default `BARGE_IN_MODE=assisted` (no STT during playback; interrupt via button/GPIO later).

---

## 5. Optional: startup chime

Place a WAV file so the service can play it once when the network is up:

- `config/chime.wav`, or  
- `data/chime.wav`

The wrapper runs `scripts/pi_net_wait_and_chime.sh` which waits for internet then plays the first of these found.

---

## 6. Enable and start the service

```bash
sudo systemctl enable threepio
sudo systemctl start threepio
```

Check status and logs:

```bash
sudo systemctl status threepio
tail -f /var/log/threepio/ambient.log
```

Or journal:

```bash
journalctl -u threepio -f
```

---

## 7. Stop and safe shutdown

Stop the service (sends SIGTERM; app stops playback and closes streams):

```bash
sudo systemctl stop threepio
```

To shut down the Pi after stopping:

```bash
sudo systemctl stop threepio
sudo shutdown -h now
```

---

## 8. Commands reference

| Action              | Command |
|---------------------|--------|
| Install             | `./scripts/pi_install.sh` |
| Audio probe         | `./scripts/pi_audio_probe.sh` |
| Edit env            | `nano config/pi.env` |
| Enable on boot      | `sudo systemctl enable threepio` |
| Start               | `sudo systemctl start threepio` |
| Stop                | `sudo systemctl stop threepio` |
| Status              | `sudo systemctl status threepio` |
| Log (file)          | `tail -f /var/log/threepio/ambient.log` |
| Log (journal)       | `journalctl -u threepio -f` |
| Reboot (after I2S)  | `sudo reboot` |

---

## 9. Log rotation

Logrotate is installed as `/etc/logrotate.d/threepio` (from `systemd/logrotate_threepio`). Logs under `/var/log/threepio/*.log` rotate daily, keep 7, compressed.

---

## 10. Troubleshooting

- **No input/capture devices**  
  Check I2S overlays and reboot. Run `arecord -l` and set `THREEPIO_AUDIO_INPUT_DEVICE` in `config/pi.env`.

- **No playback**  
  Run `aplay -l`. Set `THREEPIO_AUDIO_OUTPUT_DEVICE` or `AUDIO_OUTPUT_MODE=aplay` and ensure the DAC overlay is loaded.

- **Service exits immediately**  
  Check `/var/log/threepio/ambient.log` or `journalctl -u threepio -n 100`. Often missing API keys or wrong device names in `config/pi.env`.

- **Chime not playing**  
  Ensure `config/chime.wav` or `data/chime.wav` exists and is valid WAV. Check that `aplay` works from the command line for that file.
