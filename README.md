# THREEPIO

## 📰 Featured on Hackaday
This project has been featured on Hackaday. Article link coming soon.

---

A real-time, AI-powered conversational droid that you can actually talk to.

This project explores what happens when AI is removed from the screen and placed into a physical object—shifting interaction from typing to conversation.

🎥 Demo:  https://www.youtube.com/watch?v=wB2CJm4sHcM&feature=youtu.be 

Want to try it yourself? Get it running locally:

## 🚀 Quick Start (Run in minutes)

```bash
git clone https://github.com/spotozkin/threepio
cd threepio
pip install -r requirements.txt
python -m threepio.main --ambient

Design Principles:
- Closed-loop speech on constrained hardware (latency, echo, barge-in)
- Persona-bound dialogue (intent + tone), not generic assistant mode
- Swapping STT/LLM/TTS backends via environment configuration on hardware with limited thermal headroom

## Technical Highlights

- **Real-time audio pipeline**
  Continuous microphone input processed with low-latency speech detection and streaming transcription.

- **Ambient interaction loop**
  Designed to operate without explicit prompts, supporting natural conversation and passive listening.

- **Barge-in / interruption handling**
  Allows users to interrupt responses mid-speech, requiring coordination between playback and input streams.

- **Echo and feedback suppression**
  Prevents the system from triggering on its own voice output, a common failure mode in voice agents.

- **Persona-driven response layer**
  Separates reasoning from delivery to maintain a consistent C-3PO-inspired conversational style.

- **Embedded deployment (Raspberry Pi)**
  Full pipeline runs on-device with systemd service management and hardware-level audio integration.

- **Modular provider architecture**
  Supports interchangeable STT, LLM, and TTS backends via environment configuration.

- **Hardware + software integration**
  Combines physical fabrication, audio hardware, and AI systems into a single cohesive build.

---

## Demo

<!-- Add embed or link when ready: `[demo video](URL)` -->

---

## System Overview

```
Microphone Input
      ↓
Speech-to-Text (Whisper)
      ↓
LLM (OpenAI)
      ↓
Persona Layer (C-3PO behavior shaping)
      ↓
Text-to-Speech (ElevenLabs / OpenAI)
      ↓
Speaker Output
```

- **config** — Loads environment settings via Pydantic.
- **speech** — Handles STT/TTS and playback resolution.
- **brain + chat** — Run the LLM and tool orchestration.
- **persona** — Owns prompt construction and routing.
- **modes** — Hosts the ambient interaction loop.
- **eyes / io** — Interfaces with GPIO-backed hardware features.
- **playback** — Resolution logic lives in `threepio.speech.playback` (`docs/PLAYBACK_UNIFIED.md`).

## Why This Matters

Most AI systems today are designed for screens. THREEPIO explores what changes when interaction becomes physical, continuous, and voice-driven.

Screens hide latency and audio issues. Here they do not: playback leaks into the mic, turns overlap, and users barge in—so you tune VAD, suppression, and persona consistency on hardware where echo and thermals are real constraints.

---

## Environment files

| File | Use |
|------|-----|
| **`.env.example`** | Template for **local dev**. Copy to `.env` in the repo root and edit. Ignored by git. |
| **`config/pi.env.example`** | Template for **Pi + systemd**. Copy to `config/pi.env` on the device; the bundled systemd unit sources this path. Do not commit real keys. |

Skip `.env.template` unless you want the bare minimum; laptops should start from `.env.example`. Tunables: `docs/SETUP_BEST_EXPERIENCE.md`.

---

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env               # optional: add OPENAI_API_KEY etc.
python -m threepio
```

Text in, text out; `quit` or Ctrl+C. Defaults to mock STT/LLM/TTS—point `.env` at real providers when ready.

**Tests**

```bash
pytest
```

Clean-env tests (ignores your `.env`): `./scripts/test_clean_env.sh`

Other modes (realtime voice, ambient-only entrypoints, ElevenLabs/OpenAI TTS, NeoPixels, voice training): extra installs and env—see `docs/SETUP_BEST_EXPERIENCE.md`.

---

## Deploy on Raspberry Pi

This is the canonical deployment path used to run THREEPIO as a persistent service on a Raspberry Pi.

Matches `systemd/threepio.service`; hardware/I2S/overlays in `docs/PI_DEPLOYMENT.md`.

1. Flash **Pi OS** (64-bit), enable SSH; clone repo to **`/home/pi/threepio`**.
2. **`./scripts/pi_install.sh`** (after `chmod +x scripts/*.sh systemd/threepio_wrapper.sh`).
3. **`./scripts/pi_audio_probe.sh`** — set `THREEPIO_AUDIO_INPUT_DEVICE` / `THREEPIO_AUDIO_OUTPUT_DEVICE` in **`config/pi.env`** (from **`config/pi.env.example`**).
4. **`sudo cp systemd/threepio.service /etc/systemd/system/`**, then **`sudo systemctl daemon-reload && sudo systemctl enable --now threepio`**.
5. Logs: **`journalctl -u threepio -f`** or **`tail -f /var/log/threepio/ambient.log`** (see unit).

Use **`ffplay` / `aplay`**, not **`afplay`** (macOS-only). Full wiring and **`/boot/firmware/config.txt`** steps: **`docs/PI_DEPLOYMENT.md`**.

---

## First run & profile

First run may ask for a short profile; re-run with:

```bash
python -m threepio --setup-profile
```

Data: **`.threepio/profile.json`** (gitignored).

---

## Package layout

`src/threepio/` — **config**, **speech**, **brain**, **chat**, **persona**, **modes**, **voice**, **eyes**, **audio**, **tools**, **memory**, **runtime**.

## Status

Actively iterating — focused on improving latency, interruption handling, and embedded performance.

## Notes

This is a personal engineering project and is not affiliated with or endorsed by Lucasfilm or Disney.
