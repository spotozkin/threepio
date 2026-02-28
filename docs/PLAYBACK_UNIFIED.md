# Playback architecture (unified)

**Canonical module:** `threepio.speech.playback`

All playback resolution and `AUDIO_OUTPUT_MODE` logic lives in `threepio.speech.playback`. Ambient, streaming_chat, TTS providers, healthcheck, and speaker/output use it (or the thin shim) consistently.

## Module layout

- **`threepio.speech.playback`** – Canonical: `get_audio_output_mode()`, `get_playback_command()`, `get_playback_command_with_mode()`, `get_resolved_playback_binary()`, `play_audio_file()`, `play_audio_file_interruptible()`, `PlaybackHandle`, `resolve_playback_mode()`. Supports: `auto`, `afplay`, `ffplay`, `aplay`, `mpg123`, `print`. `play` is accepted as alias for `auto`; error messages never suggest `AUDIO_OUTPUT_MODE=play`.
- **`threepio.audio.playback`** – Shim: re-exports from `threepio.speech.playback` for backward compatibility.
- **`threepio.audio.player`** – Thin wrapper: `play_audio(path)` → `play_audio_file(path)` from speech.playback.

Removed: `threepio.audio.playback_proc` (duplicate implementation).

## Callers (all use same resolver)

- **ambient** – `from threepio.speech.playback import PlaybackHandle, play_audio_file_interruptible`, `get_playback_command_with_mode` for probe.
- **streaming_chat** – Uses TTS from `get_tts_provider()`; OpenAI TTS uses `MacSpeakerOutput` → `play_audio_file` (speech.playback); ElevenLabs uses `play_audio_file_interruptible` (speech.playback).
- **main.py (TTS test)** – `from threepio.speech.playback import play_audio_file`.
- **io/speaker.py**, **audio/output.py** – `from threepio.speech.playback import play_audio_file`.
- **speech/tts/provider.py** – Uses `getattr(settings, "AUDIO_OUTPUT_MODE", "auto")`; speaker choice uses same mode.
- **core/healthcheck** – `from threepio.speech.playback import get_resolved_playback_binary` for playback binary check.

## macOS afplay

If `shutil.which("afplay")` is None (e.g. minimal PATH), `_which("afplay")` falls back to `/usr/bin/afplay` on darwin when the file exists and is executable.

## Debug

With `THREEPIO_DEBUG=1`, playback logs: resolved mode, binary path, and when no player is found.

## Validation commands (macOS)

```bash
# 1) Streaming chat – TTS plays via AUDIO_OUTPUT_MODE
AUDIO_OUTPUT_MODE=afplay python -m threepio.chat.streaming_chat

# 2) Ambient – TTS plays
THREEPIO_AUDIO_INPUT_DEVICE=1 AUDIO_OUTPUT_MODE=afplay python -c "import threepio.modes.ambient as m; m.run_ambient()"

# 3) Ambient with C-3PO FX (no crash)
ENABLE_C3PO_FX=true AUDIO_OUTPUT_MODE=afplay python -c "import threepio.modes.ambient as m; m.run_ambient()"
```

Use `AUDIO_OUTPUT_MODE=print` to disable actual audio and only print.
