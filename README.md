# THREEPIO (C-3PO Head AI)

A Pi-compatible Python project for a C-3PO-style conversational AI head.

## Setup

```bash
# Create and activate venv
python -m venv .venv
source .venv/bin/activate

# Install package (editable) with dev deps
pip install -e ".[dev]"

# Copy env template
cp .env.example .env
```

## Run

```bash
source .venv/bin/activate
python -m threepio
```

Type messages and press Enter. Type `quit` to exit. Ctrl+C for clean shutdown.

### Example prompts

THREEPIO responds to tools (time, weather, stocks) and uses mock data by default:

- `what time is it` – returns local time
- `weather in Anaheim` – returns mock weather for that location
- `stock price of NVDA` – returns mock stock price

Set `REAL_TOOLS=1` to use real APIs (Yahoo Finance, wttr.in) when available.

## Run Tests

```bash
source .venv/bin/activate
pytest
```

**Deterministic runs (no direnv / .env):** from project root, run `./scripts/test_clean_env.sh` to run pytest with a clean environment so local secrets don't affect results.

## OpenAI TTS

To use real voice synthesis instead of printed output:

1. Install the OpenAI extra: `pip install -e ".[dev,openai]"`
2. Add to `.env`:
   - `OPENAI_API_KEY=sk-your-key`
   - `PROVIDER_TTS=openai`
   - `TTS_VOICE=alloy` (optional, default)
   - `TTS_MODEL=gpt-4o-mini-tts` (optional, default)
   - `AUDIO_OUTPUT_MODE=auto` or `afplay` (macOS: plays via afplay; use `print` to only print)

Without `OPENAI_API_KEY` or with `PROVIDER_TTS=mock`, the app automatically uses MockTTS.

## Realtime voice (ChatGPT-style, streaming, barge-in)

Uses the OpenAI Realtime API over WebSockets for low-latency voice conversation.

```bash
# Install realtime extra (openai, websockets, sounddevice, numpy)
pip install -e ".[dev,realtime]"

# Run in mock mode (typed lines, no mic) – dev-friendly
export OPENAI_API_KEY=sk-your-key
export PROVIDER_VOICE=realtime
export AUDIO_INPUT_MODE=mock
export AUDIO_OUTPUT_MODE=print
python -m threepio

# Run with mic + playback
export AUDIO_INPUT_MODE=mic
export AUDIO_OUTPUT_MODE=afplay
python -m threepio
```

Requires: `OPENAI_API_KEY`, `PROVIDER_VOICE=realtime`, and the realtime extra.  
Without these, the app falls back to CLI mode (`PROVIDER_VOICE=cli`).

## Ambient voice (laptop demo)

Continuous listen → STT → LLM → TTS with barge-in. Use these env vars and run:

```bash
# Mic device (sounddevice index or name substring); optional
export THREEPIO_AUDIO_INPUT_DEVICE=1

# Min speech duration before sending to STT (seconds); default 1.2
export THREEPIO_MIN_UTTERANCE_SEC=0.7

# C-3PO voice post-processing (ffmpeg chain)
export ENABLE_C3PO_FX=true

# Run ambient (debug + afplay for laptop)
THREEPIO_DEBUG=1 AUDIO_OUTPUT_MODE=afplay python -m threepio.modes.ambient
```

Or via main entry: `python -m threepio --ambient`. Override mic with `--device-in N`; otherwise `THREEPIO_AUDIO_INPUT_DEVICE` or system default is used. Ambient runs without crashing even if some settings fields are missing (defensive `getattr` where needed).

VAD tuning: `THREEPIO_VAD_START_RMS` (float, default 0.004), `THREEPIO_VAD_COOLDOWN_MS` (int, default 400), `THREEPIO_VAD_AGGR` (0–3, default 2), `THREEPIO_MIN_UTTERANCE_SEC` (float; env overrides settings). These are read in one place each (vad.py or ambient) and used consistently.

### Validating on macOS

```bash
# A) VAD-test mode (no STT/LLM/TTS): 10s mic capture, print rms/peak and would_accept
python -m threepio --vad-test

# B) Ambient with print (no audio playback)
AUDIO_OUTPUT_MODE=print python -m threepio --ambient

# C) Ambient with afplay (play TTS through speakers)
AUDIO_OUTPUT_MODE=afplay python -m threepio --ambient
```

Use `THREEPIO_DEBUG=1` for detailed VAD/reject logs (reason, rms, threshold, cooldown_remaining_ms, device_index, sample_rate).

## Eyes (C-3PO amber glow)

### Laptop (no hardware)

```bash
PROVIDER_EYES=mock
```

Eyes print `[EYES] ON` / `[EYES] OFF` to the console.

### Raspberry Pi + Adafruit NeoPixel

```bash
pip install -e ".[neopixel]"
```

Then in `.env`:

```
PROVIDER_EYES=neopixel
EYES_PIN=D18
EYES_PIXEL_COUNT=<total pixels in chain>
```

Optional: `EYES_BRIGHTNESS=0.35`, `EYES_AMBER_RGB=255,150,40`, `EYES_CHAIN_MODE=single`

Run `python -m threepio`. Eyes stay ON (static warm amber glow) while running; OFF on quit or Ctrl+C.

## Local voice training (your voice)

Train THREEPIO to speak in your own voice (consented recordings). **No heavy ML deps in the main venv** – training runs in a separate venv.

### Recording guidelines

- **Format**: WAV or MP3, mono preferred, 16–44.1 kHz
- **Duration**: ~30–60 min total; segments ~5–15 sec each
- **Environment**: Quiet room, minimal background noise
- **Content**: Diverse phrases, natural pacing, clear articulation

### Separate training venv

```bash
python3 -m venv .venv-train
source .venv-train/bin/activate
pip install -e ".[dev]"  # plus ML deps when Track is chosen
```

### Pipeline

```bash
# From project root, with .venv-train activated:
source .venv-train/bin/activate

# 1. Preprocess raw recordings
python -m threepio.voice.dataset.preprocess --in data/voice_raw --out data/voice_clean
# Input:  data/voice_raw/
# Output: data/voice_clean/wavs/ + data/voice_clean/metadata.csv

# 2. Transcribe (replace __TRANSCRIBE_ME__ with ASR output)
pip install faster-whisper
python -m threepio.voice.dataset.transcribe --dataset data/voice_clean --model base --language en

# 3. Validate dataset
python -m threepio.voice.training.train_cli
```

### Transcription (local)

Uses faster-whisper for ASR. Runs only in `.venv-train`.

```bash
source .venv-train/bin/activate
pip install faster-whisper
python -m threepio.voice.dataset.transcribe --dataset data/voice_clean --model base --language en
```

- Reads `metadata.csv`; rows with `__TRANSCRIBE_ME__` are transcribed.
- Backs up to `metadata.csv.bak` before overwriting.
- Writes `transcribe_report.json` (total_clips, transcribed, skipped, avg_confidence, model_name).
- Resume-safe: skips already-transcribed rows.

## Project Structure

- `src/threepio/` - Main package
- `src/threepio/runtime/` - State machine, lifecycle, logging
- `src/threepio/memory/` - Conversation memory (rolling window)
- `src/threepio/tools/` - Tool router (time, weather, stocks)
- `src/threepio/input/` - Input event providers (console, buttons, encoder)
- `src/threepio/brain/` - Response generation, dialogue, LLM
- `src/threepio/voice/` - Local voice training, realtime (OpenAI Realtime API)
- `src/threepio/config/` - Settings (Pydantic)
- `src/threepio/core/` - Logging, types
- `src/threepio/eyes/` - C-3PO eye glow (NeoPixel or mock)
- `src/threepio/io/` - LED drivers
- `src/threepio/speech/` - STT/TTS (base + implementations)
- `src/threepio/character/` - Persona rules

---

## Exact run commands

```bash
# Base CLI (text input, no realtime)
python -m threepio

# Run tests
pytest -q

# Realtime voice (mock input, print output – no headphones)
pip install -e ".[dev,realtime]"
export OPENAI_API_KEY=sk-your-key
export PROVIDER_VOICE=realtime
export AUDIO_INPUT_MODE=mock
export AUDIO_OUTPUT_MODE=print
python -m threepio

# Realtime voice (mic + play)
export AUDIO_INPUT_MODE=mic
export AUDIO_OUTPUT_MODE=afplay
python -m threepio

# Ambient voice (laptop demo: input device, min utterance, C-3PO FX)
export THREEPIO_AUDIO_INPUT_DEVICE=1
export THREEPIO_MIN_UTTERANCE_SEC=0.7
export ENABLE_C3PO_FX=true
THREEPIO_DEBUG=1 AUDIO_OUTPUT_MODE=afplay python -m threepio.modes.ambient
```
# C3P0

## First-Time Setup

On first run, THREEPIO will prompt you to configure your user profile in the terminal.

To manually re-run setup:

    python -m src.threepio.main --setup-profile

Profile data is stored locally in:

    .threepio/profile.json

Deleting the `.threepio/` directory resets configuration.
