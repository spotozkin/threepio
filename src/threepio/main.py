"""Main entry point: CLI with --tts-test and default app entry."""

from __future__ import annotations

import argparse
import sys
from typing import Any, NoReturn

from threepio.memory.user_profile import load_or_prompt_profile

__all__ = ["main"]


def _parse_args():
    parser = argparse.ArgumentParser(
        description="THREEPIO",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tts-test",
        action="store_true",
        help="Run TTS test: generate one line via configured provider, save to data/tts/, apply C-3PO FX if available, play per AUDIO_OUTPUT_MODE.",
    )
    parser.add_argument(
        "--healthcheck",
        action="store_true",
        help="Run startup validation and capability probe; exit 0 if OK, 1 otherwise.",
    )
    parser.add_argument(
        "--ambient",
        action="store_true",
        help="Run ambient mode: continuous listen, TTS response, barge-in.",
    )
    parser.add_argument(
        "--device-in",
        type=int,
        default=None,
        metavar="INT",
        help="Override mic device index. Default: THREEPIO_AUDIO_INPUT_DEVICE or system default.",
    )
    parser.add_argument(
        "--vad-threshold",
        type=float,
        default=None,
        metavar="FLOAT",
        help="Optional VAD silence threshold (ms) before speech end. Default: use module default.",
    )
    parser.add_argument(
        "--vad-test",
        action="store_true",
        help="Run mic capture 10s and print rms/peak and whether speech would be accepted (no STT/LLM/TTS). Tune THREEPIO_VAD_START_RMS.",
    )
    parser.add_argument(
        "--setup-profile",
        action="store_true",
        help="Run interactive profile setup and exit",
    )
    parser.add_argument(
        "--list-audio-devices",
        action="store_true",
        help="List available audio input devices and exit.",
    )
    return parser.parse_known_args()


def _run_tts_test() -> int:
    """Generate one TTS line via get_tts_provider().synthesize(), save to data/tts/, apply FX if present, play per AUDIO_OUTPUT_MODE."""
    import os
    from pathlib import Path

    from threepio.config import get_settings

    settings = get_settings()
    provider_name = (settings.PROVIDER_TTS or "").strip().lower()
    if provider_name not in ("openai", "elevenlabs"):
        print(
            "TTS test failed: PROVIDER_TTS must be 'openai' or 'elevenlabs' (got {!r}). "
            "Set PROVIDER_TTS in .env or .envrc.".format(provider_name or "(empty)"),
            flush=True,
        )
        return 1

    try:
        from threepio.speech.tts.provider import get_tts_provider
        provider = get_tts_provider()
    except (ValueError, TypeError) as e:
        print(f"TTS test failed: {e}", flush=True)
        return 1

    out_dir = Path("data/tts")
    out_dir.mkdir(parents=True, exist_ok=True)
    ext = ".mp3" if provider_name == "openai" else (
        ".mp3" if "mp3" in str(getattr(settings, "ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128") or "").lower() else ".wav"
    )
    raw_path = out_dir / ("tts_test" + ext)
    fx_path = out_dir / ("tts_test_fx" + ext)

    try:
        audio_bytes = provider.synthesize("Hello. This is a TTS test.")
    except Exception as e:
        print(f"TTS test failed: {e}", flush=True)
        return 1

    if not audio_bytes or len(audio_bytes) < 128:
        print(
            f"TTS test failed: provider returned too little audio ({len(audio_bytes) if audio_bytes else 0} bytes).",
            flush=True,
        )
        return 1

    # Atomic-ish write: temp then rename
    tmp_path = out_dir / (raw_path.stem + ".tmp" + raw_path.suffix)
    tmp_path.write_bytes(audio_bytes)
    tmp_path.replace(raw_path)

    if os.environ.get("THREEPIO_DEBUG", "").strip().lower() in ("1", "true", "yes", "on"):
        print(f"[TTS test] saved path={raw_path.resolve()} bytes={len(audio_bytes)}", flush=True)

    # Reject suspiciously small output (invalid or placeholder)
    if len(audio_bytes) < 1000:
        print(
            f"TTS test failed: output too small ({len(audio_bytes)} bytes). First 64 bytes: {audio_bytes[:64]!r}",
            flush=True,
        )
        return 1

    # Apply C-3PO FX (ffmpeg). Raw file already saved; on FX failure skip with clear message, exit 0.
    applied_fx = False
    try:
        from threepio.speech.tts.c3po_fx import apply_c3po_fx
        apply_c3po_fx(str(raw_path), str(fx_path))
        applied_fx = True
    except Exception as e:
        print(f"[FX] skipped: {e}", flush=True)

    mode = settings.AUDIO_OUTPUT_MODE
    if mode == "print":
        print(f"TTS test files: {raw_path.resolve()}" + (f", {fx_path.resolve()}" if applied_fx else ""), flush=True)
    else:
        from threepio.speech.playback import play_file
        fx_ok = applied_fx and fx_path.exists() and fx_path.stat().st_size >= 128
        play_path = fx_path if fx_ok else raw_path
        if play_path == raw_path:
            print("[FX] skipped, playing raw", flush=True)
        try:
            play_file(play_path)
        except Exception as e:
            print(f"TTS test playback failed: {e}", flush=True)
            return 1

    print("TTS test complete: " + str(raw_path) + (f" (FX: {fx_path})" if applied_fx else ""), flush=True)
    return 0


def _run_healthcheck() -> int:
    """Run startup checks, print report, return 0 if ok else 1."""
    from threepio.config import get_settings
    from threepio.core.healthcheck import print_report, run_startup_checks

    settings = get_settings()
    try:
        report = run_startup_checks(settings)
    except RuntimeError as e:
        print(f"Healthcheck failed: {e}", flush=True)
        return 1
    print_report(report)
    return 0 if report.get("ok") else 1


def _run_ambient(settings: Any, device_in: int | None = None, vad_threshold: float | None = None) -> int:
    """Run ambient mode loop; blocks until exit. Returns 0 if normal, 1 if startup failed."""
    from threepio.modes.ambient import run as ambient_run
    return ambient_run(settings, device_in=device_in, vad_threshold=vad_threshold)


def _run_list_audio_devices() -> None:
    """Print audio input devices (max_input_channels > 0) to stdout."""
    from threepio.audio.devices import format_input_devices, list_input_devices

    devs = list_input_devices()
    if not devs:
        print("No audio input devices found.", flush=True)
    else:
        print(format_input_devices(devs), flush=True)


def main() -> NoReturn:
    """Parse CLI; run --healthcheck, --tts-test, or --ambient before other modes, else run app."""
    args, _ = _parse_args()
    if args.setup_profile:
        from threepio.memory.user_profile import prompt_profile, save_profile_file
        profile = prompt_profile()
        save_profile_file(profile)
        return
    if getattr(args, "list_audio_devices", False):
        _run_list_audio_devices()
        sys.exit(0)
    profile = load_or_prompt_profile()
    if getattr(args, "healthcheck", False):
        code = _run_healthcheck()
        sys.exit(code)
    if getattr(args, "tts_test", False):
        code = _run_tts_test()
        sys.exit(code)
    if getattr(args, "vad_test", False):
        from threepio.modes.ambient import run_vad_test
        run_vad_test(device_in=getattr(args, "device_in", None))
        sys.exit(0)
    if getattr(args, "ambient", False):
        from threepio.config import get_settings
        settings = get_settings()
        code = _run_ambient(
            settings,
            device_in=getattr(args, "device_in", None),
            vad_threshold=getattr(args, "vad_threshold", None),
        )
        sys.exit(code)

    # Startup validation: run checks and print concise report before app
    from threepio.config import get_settings
    from threepio.core.healthcheck import print_report, run_startup_checks

    settings = get_settings()
    try:
        report = run_startup_checks(settings)
        print_report(report)
    except RuntimeError as e:
        print(f"Startup check failed: {e}", flush=True)
        sys.exit(1)

    from threepio.app import main as app_main
    app_main()


if __name__ == "__main__":
    main()
