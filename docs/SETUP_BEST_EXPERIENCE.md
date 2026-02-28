# THREEPIO: Files & Setup for Best / Most Accurate Experience

This document lists **missing or optional files and docs** that improve realism, accuracy, and feature coverage. Nothing here is required to run the app (mock providers work out of the box).

---

## 1. Configuration (required for non-mock modes)

| Item | Purpose | Where |
|------|---------|--------|
| **`.env`** | API keys and provider choices; not in git | Copy from `.env.example`, fill in keys |
| **`OPENAI_API_KEY`** | Realtime voice, OpenAI TTS, LLM, Whisper API | `.env` |
| **`ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `ELEVENLABS_MODEL_ID`** | ElevenLabs TTS + C-3PO-style voice | `.env` when `PROVIDER_TTS=elevenlabs` |

Without these, THREEPIO runs with mock STT/LLM/TTS (text-only or printed output).

---

## 2. Optional persona / memory modules (ambient still runs without them)

These are **referenced by ambient mode** but have **safe fallbacks** if missing:

| Module | Role | If missing |
|--------|------|------------|
| **`threepio.persona.reality_threepio`** | `slang_to_formal_gloss` for slang→formal | Fallback: no gloss; `semantic_filter.interpret_user_intent` still used |
| **`threepio.memory.notes`** | `add_note`, `extract_note_from_user_text`, `should_save_note` | Fallback: no-ops; no note-taking |

**Present and used:** `persona_spec`, `semantic_filter`, `prompt_builder`, `address_gating`, `c3po_governor`, `flavor_governor`, `memory.user_profile`.

To get the **most accurate C-3PO experience**, ensure the **persona pack** is in use (it is in code; no extra files). Optional: add `reality_threepio.py` for extra slang→formal gloss and `memory/notes.py` for note-taking if you want those behaviors.

---

## 3. Data directories and generated files

| Path | Purpose | Created by |
|------|---------|------------|
| **`data/tts/`** | TTS test and ambient output (e.g. `tts_test.mp3`, `tts_test_fx.mp3`) | App / `--tts-test` |
| **`data/voice/`** | Voice training outputs, XTTS reference WAV | You / pipeline |
| **`data/memory/`** | User profiles (`profiles.json`) | `memory.user_profile` on first save |
| **`data/memory/voiceprints/`** | Speaker embeddings for voice ID | `identity.voice_id` enrollment |
| **`data/voice_raw/`** | Raw recordings for voice training | You |
| **`data/voice_clean/`** | Processed dataset (wavs + `metadata.csv`) | `threepio.voice.dataset.preprocess` |

For **best experience**: create `data/tts` and `data/memory` (app can create them; healthcheck expects writable `data/tts`, `data/voice`). For **voice cloning / retrieval TTS**, add `data/voice_clean` with `metadata.csv` and WAVs (see README “Local voice training”).

---

## 4. External tools and repos

| Dependency | Used for | When required |
|-------------|----------|----------------|
| **ffmpeg** | C-3PO FX (canonical chain), playback (ffplay) | `PROVIDER_TTS` in (openai, elevenlabs) or `AUDIO_OUTPUT_MODE=ffplay` |
| **faster-whisper** | Local STT in ambient | `--ambient` with local Whisper (install in venv) |
| **Resemblyzer** | Speaker ID (voiceprints) in ambient | Optional; only if using voice ID in ambient |
| **RVC (tools/rvc/)** | RVC voice conversion (e.g. after XTTS) | Only if `ENABLE_RVC=1` and RVC configured |

**Best experience:** Install `ffmpeg` for C-3PO FX and real TTS playback. For ambient with local STT, install `faster-whisper`.

---

## 5. TTS / voice assets for “most realistic” voice

| Asset | Purpose | How to get |
|-------|---------|------------|
| **Retrieval TTS dataset** | `metadata.csv` + WAVs in `LOCAL_VOICE_DATASET_DIR` | Voice training pipeline (preprocess → transcribe) or hand-built clips |
| **XTTS reference WAV** | Single reference for XTTS clone | e.g. `data/voice/processed/c3po_sam/reference.wav`; record or export from training |
| **ElevenLabs voice** | High-quality C-3PO-style TTS | Configure `ELEVENLABS_VOICE_ID` + `ELEVENLABS_MODEL_ID` in `.env` |
| **C-3PO FX** | Canonical “droid” tone (compressor, echo, limiter) | No extra files; enable in app, requires ffmpeg |

---

## 6. Documentation that would help (currently missing or minimal)

| Document | Would cover |
|----------|-------------|
| **Persona / behavior** | How the C-3PO persona is defined (persona_spec, semantic_filter, prompt_builder), and how to tune without breaking character. |
| **Ambient mode** | Mic setup, VAD, `--ambient`, `--device-in`, `--vad-threshold`, STT (faster-whisper vs API), and how persona + memory interact. |
| **Voice pipeline** | End-to-end: record → preprocess → transcribe → train → use with retrieval/XTTS/local_voice. |
| **Pi deployment** | `DEPLOY_PI.md` exists; could add a short “best experience on Pi” (env, providers, audio devices). |
| **.env.example** | Already documents many options; could add one-line notes for `PROVIDER_TTS=retrieval`, `PROVIDER_TTS=xtts`, `LOCAL_VOICE_DATASET_DIR`, `XTTS_REFERENCE_WAV`. |

Adding these would make it easier to get the **best and most accurate** setup without reading code.

---

## 7. Quick checklist for “best version” and “most accurate experience”

- [ ] **`.env`** from `.env.example` with real keys for the providers you use (OpenAI and/or ElevenLabs for voice/LLM).
- [ ] **ffmpeg** installed (C-3PO FX + playback).
- [ ] **`data/tts`** and **`data/memory`** writable (or let the app create them).
- [ ] **Persona** is already in code (persona_spec, semantic_filter, prompt_builder); no extra “persona documents” required.
- [ ] For **ambient**: install **faster-whisper** (or use API STT) and set `PROVIDER_STT`; optionally Resemblyzer for voice ID.
- [ ] For **C-3PO voice**: use **ElevenLabs** or **OpenAI TTS** + C-3PO FX; or **retrieval/XTTS** with a prepared dataset/reference WAV.
- [ ] Optional: **`threepio.memory.notes`** and **`threepio.persona.reality_threepio`** if you want note-taking and extra slang gloss (ambient works without them).
- [ ] Optional: **RVC** under `tools/rvc/` only if you use RVC voice conversion.

No **runtime script loading** is used for the persona; everything is code and data in the repo plus your `.env` and data directories.
