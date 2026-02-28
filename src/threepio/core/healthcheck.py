"""Startup validation and capability probe. Run before main app or via --healthcheck."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

# Default data dirs the app may write to
DATA_DIRS = ("data/tts", "data/voice")


def _getattr_str(obj: Any, name: str) -> str:
    """Return stripped string from obj.name; missing, non-string (e.g. MagicMock), or falsy -> ''."""
    val = getattr(obj, name, None)
    if isinstance(val, str):
        return val.strip()
    return ""


def run_startup_checks(
    settings: Any,
    *,
    which_func: Callable[[str], str | None] | None = None,
    data_dirs: tuple[str, ...] = DATA_DIRS,
    cwd: Path | str | None = None,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Run startup validation and capability probe. Returns a report dict.
    Raises RuntimeError if PROVIDER_TTS==elevenlabs and required ElevenLabs env vars are missing.
    env: optional env mapping; if None, uses os.environ (under pytest uses a snapshot to respect monkeypatch).
    """
    base = Path(cwd or ".").resolve()
    if env is None:
        env = dict(os.environ) if "PYTEST_CURRENT_TEST" in os.environ else os.environ
    report: dict[str, Any] = {
        "ok": True,
        "providers": {},
        "binaries": {},
        "dirs": {},
        "errors": [],
    }

    # 1) Provider selection summary (Pydantic already validates; provide readable summary)
    p_tts = (getattr(settings, "PROVIDER_TTS", None) or "").strip().lower()
    p_stt = (getattr(settings, "PROVIDER_STT", None) or "").strip().lower()
    p_llm = (getattr(settings, "PROVIDER_LLM", None) or "").strip().lower()
    report["providers"] = {"tts": p_tts or "(empty)", "stt": p_stt or "(empty)", "llm": p_llm or "(empty)"}

    # 2) ElevenLabs: require API_KEY, VOICE_ID, MODEL_ID (settings then env fallback)
    if p_tts == "elevenlabs":
        api_key = _getattr_str(settings, "ELEVENLABS_API_KEY") or (env.get("ELEVENLABS_API_KEY", "") or "").strip()
        voice_id = _getattr_str(settings, "ELEVENLABS_VOICE_ID") or (env.get("ELEVENLABS_VOICE_ID", "") or "").strip()
        model_id = _getattr_str(settings, "ELEVENLABS_MODEL_ID") or (env.get("ELEVENLABS_MODEL_ID", "") or "").strip()
        if not api_key or not voice_id or not model_id:
            raise RuntimeError(
                "ElevenLabs misconfigured: missing ELEVENLABS_API_KEY/ELEVENLABS_VOICE_ID/ELEVENLABS_MODEL_ID"
            )

    # 3) STT uses OpenAI (whisper etc.) -> OPENAI_API_KEY required on settings; do not raise
    if p_stt in ("whisper", "openai_whisper_api", "openai"):
        openai_key = _getattr_str(settings, "OPENAI_API_KEY")
        if not openai_key:
            report["errors"].append("PROVIDER_STT=whisper requires OPENAI_API_KEY")

    # 4) External binaries: ffmpeg (if C3PO FX or ffplay used), playback backend (canonical: speech.playback)
    from threepio.speech.playback import get_resolved_playback_binary

    c3po_fx_used = p_tts in ("openai", "elevenlabs")
    audio_mode = getattr(settings, "AUDIO_OUTPUT_MODE", "auto") or "auto"
    playback_path = get_resolved_playback_binary(audio_mode)
    playback_bin = Path(playback_path).name if playback_path else None

    which = which_func if which_func is not None else (lambda c: __import__("shutil").which(c))
    ffmpeg_ok = which("ffmpeg") is not None
    report["binaries"]["ffmpeg"] = ffmpeg_ok
    if c3po_fx_used and not ffmpeg_ok:
        report["errors"].append("C3PO FX (or ffplay) requires ffmpeg. Install ffmpeg.")
        report["ok"] = False

    report["binaries"]["playback"] = playback_bin or "print"
    if audio_mode != "print" and not playback_bin:
        report["errors"].append(
            f"AUDIO_OUTPUT_MODE={audio_mode} but no playback binary found (afplay/ffplay/aplay/mpg123 or use print)"
        )
        report["ok"] = False

    # 5) Data directories exist and writable
    for rel in data_dirs:
        d = (base / rel).resolve()
        try:
            d.mkdir(parents=True, exist_ok=True)
            probe = d / ".healthcheck_write_probe"
            probe.write_text("")
            probe.unlink()
            report["dirs"][rel] = True
        except OSError as e:
            report["dirs"][rel] = False
            report["errors"].append(f"Directory {rel} not writable: {e}")

    report["ok"] = len(report["errors"]) == 0
    return report


def print_report(report: dict[str, Any], verbose: bool = False) -> None:
    """Print a concise healthcheck report to stdout."""
    if report.get("ok"):
        print("Healthcheck OK", flush=True)
    else:
        print("Healthcheck FAILED", flush=True)
    for k, v in report.get("providers", {}).items():
        print(f"  {k}: {v}", flush=True)
    for k, v in report.get("binaries", {}).items():
        print(f"  {k}: {v}", flush=True)
    for rel, ok in report.get("dirs", {}).items():
        print(f"  dir {rel}: {'ok' if ok else 'FAIL'}", flush=True)
    for err in report.get("errors", []):
        print(f"  ERROR: {err}", flush=True)
    if verbose and report.get("ok"):
        print("  (all checks passed)", flush=True)
