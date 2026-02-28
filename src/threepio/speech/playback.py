"""Cross-platform audio playback: afplay (macOS), ffplay/aplay/mpg123 (Linux). Canonical module for AUDIO_OUTPUT_MODE."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Error message when no player is available (never suggest AUDIO_OUTPUT_MODE=play)
NO_PLAYER_MESSAGE = "No playback player. Set AUDIO_OUTPUT_MODE=auto, afplay, ffplay, aplay, mpg123, or print."
_NO_PLAYER_MSG = NO_PLAYER_MESSAGE

__all__ = [
    "NO_PLAYER_MESSAGE",
    "PlaybackHandle",
    "resolve_audio_output_mode",
    "resolve_player_binary",
    "resolve_player",
    "play_file",
    "stop_playback",
    "get_audio_output_mode",
    "get_playback_command",
    "get_playback_command_with_mode",
    "play_audio_file",
    "play_audio_file_interruptible",
    "resolve_playback_mode",
]


class PlaybackHandle:
    """Handle to a playback subprocess; call stop() to interrupt (barge-in). Safe to call stop() multiple times."""

    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process

    def stop(self) -> None:
        """Terminate playback immediately (terminate then kill fallback)."""
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=0.3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                self._process.kill()
            except ProcessLookupError:
                pass
        finally:
            self._process = None

    def is_running(self) -> bool:
        """True if process is still running."""
        return self._process is not None and self._process.poll() is None

# Modes: auto (platform default), afplay, ffplay, aplay, mpg123, print (no playback). "play" -> auto.
AUDIO_OUTPUT_MODES = ("auto", "afplay", "ffplay", "aplay", "mpg123", "print")


def _debug_enabled() -> bool:
    v = os.environ.get("THREEPIO_DEBUG", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def resolve_audio_output_mode() -> str:
    """Resolve AUDIO_OUTPUT_MODE from env. Accepts: auto, afplay, ffplay, aplay, mpg123, print. Treat 'play' as 'auto' for backward compat."""
    mode = (os.environ.get("AUDIO_OUTPUT_MODE") or "auto").strip().lower()
    if mode == "play":
        mode = "auto"
    if mode not in AUDIO_OUTPUT_MODES:
        mode = "auto"
    return mode


def get_audio_output_mode() -> str:
    """Backward-compat alias for resolve_audio_output_mode()."""
    return resolve_audio_output_mode()


def _which(cmd: str) -> str | None:
    """Return path to executable or None."""
    import shutil
    path = shutil.which(cmd)
    if path:
        return path
    # macOS: afplay is often at /usr/bin/afplay even when PATH is minimal
    if cmd == "afplay" and sys.platform == "darwin":
        fallback = "/usr/bin/afplay"
        if os.path.isfile(fallback) and os.access(fallback, os.X_OK):
            return fallback
    return None


def _suffix(path: Path) -> str:
    return path.suffix.lower().lstrip(".") if path.suffix else ""


def resolve_playback_mode(mode: str, path: str | Path) -> str:
    """
    Resolve which player name would be used for the given mode and path.
    Returns player name: "afplay", "ffplay", "aplay", "mpg123", "print", or "none"/"*(unavailable)".
    """
    _, player_name = get_playback_command_with_mode(path, mode)
    return player_name


def get_playback_command_with_mode(path: str | Path, mode: str) -> Tuple[list[str] | None, str]:
    """
    Same as get_playback_command but use explicit mode instead of env.
    Returns (command_args, player_name).
    """
    path = Path(path)
    if not path.exists():
        return (None, "none")
    mode = (mode or "auto").strip().lower()
    if mode == "play":
        mode = "auto"
    if mode not in AUDIO_OUTPUT_MODES:
        mode = "auto"

    is_darwin = sys.platform == "darwin"
    suffix = _suffix(path)

    def prefer_ffplay() -> list[str] | None:
        if _which("ffplay"):
            return ["ffplay", "-nodisp", "-autoexit", "-loglevel", "error", str(path)]
        return None

    def prefer_aplay() -> list[str] | None:
        if suffix in ("wav", "") and _which("aplay"):
            return ["aplay", "-q", str(path)]
        return None

    def prefer_mpg123() -> list[str] | None:
        if suffix in ("mp3", "") and _which("mpg123"):
            return ["mpg123", "-q", str(path)]
        return None

    if mode == "print":
        return (None, "print")
    if mode == "afplay":
        afplay_path = _which("afplay")
        if afplay_path:
            if _debug_enabled():
                print(f"[playback] resolved mode=afplay binary={afplay_path}", flush=True)
            return ([afplay_path, str(path)], "afplay")
        return (None, "afplay(unavailable)")
    if mode == "ffplay":
        cmd = prefer_ffplay()
        return (cmd, "ffplay") if cmd else (None, "ffplay(unavailable)")
    if mode == "aplay":
        cmd = prefer_aplay()
        return (cmd, "aplay") if cmd else (None, "aplay(unavailable)")
    if mode == "mpg123":
        cmd = prefer_mpg123()
        return (cmd, "mpg123") if cmd else (None, "mpg123(unavailable)")
    # auto
    if is_darwin:
        afplay_path = _which("afplay")
        if afplay_path:
            if _debug_enabled():
                print(f"[playback] resolved mode=auto binary={afplay_path}", flush=True)
            return ([afplay_path, str(path)], "afplay")
        return (None, "afplay(unavailable)")
    cmd = prefer_ffplay()
    if cmd:
        return (cmd, "ffplay")
    cmd = prefer_aplay()
    if cmd:
        return (cmd, "aplay")
    cmd = prefer_mpg123()
    if cmd:
        return (cmd, "mpg123")
    return (None, "none(unavailable)")


def resolve_player_binary(mode: str) -> Optional[str]:
    """If mode=auto: choose afplay on macOS if available, else ffplay/aplay/mpg123. If mode=print: return None. Else verify binary exists (shutil.which). Return binary path or None."""
    mode = (mode or "auto").strip().lower()
    if mode == "play":
        mode = "auto"
    if mode not in AUDIO_OUTPUT_MODES:
        mode = "auto"
    if mode == "print":
        return None
    if mode == "afplay":
        return _which("afplay")
    if mode == "ffplay":
        return _which("ffplay")
    if mode == "aplay":
        return _which("aplay")
    if mode == "mpg123":
        return _which("mpg123")
    # auto
    if sys.platform == "darwin":
        return _which("afplay")
    for cmd in ("ffplay", "aplay", "mpg123"):
        path = _which(cmd)
        if path:
            return path
    return None


def get_resolved_playback_binary(mode: str) -> str | None:
    """Backward-compat alias for resolve_player_binary()."""
    return resolve_player_binary(mode)


def resolve_player() -> Optional[str]:
    """Backward-compat: return the binary path that would be used for playback, or None for print/unavailable."""
    mode = resolve_audio_output_mode()
    path = resolve_player_binary(mode)
    if _debug_enabled():
        print(f"[playback] resolve_player mode={mode} binary={path or 'None'}", flush=True)
    return path


def play_file(path: str | Path, *, mode: Optional[str] = None, block: bool = True) -> None:
    """Play audio file using the resolved player (afplay/ffplay/aplay/mpg123). If mode resolves to None (print/no player), raise RuntimeError with message referencing AUDIO_OUTPUT_MODE=auto/afplay/ffplay etc (NOT 'play')."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")
    mode = mode or resolve_audio_output_mode()
    cmd, player_name = get_playback_command_with_mode(path, mode)
    if _debug_enabled():
        binary = cmd[0] if cmd else None
        print(f"[playback] play_file mode={mode} binary={binary or 'None'} path={path}", flush=True)
    if cmd is None:
        raise RuntimeError(_NO_PLAYER_MSG)
    if block:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_playback() -> None:
    """Best-effort stop of any process-based playback. No-op if no shared handle (ambient uses PlaybackHandle.stop() per session)."""
    pass


def get_playback_command(path: str | Path) -> Tuple[list[str] | None, str]:
    """
    Resolve playback command for the given file path.
    Returns (command_args, player_name). command_args is None if no playback (print mode or unavailable).
    """
    cmd, player_name = get_playback_command_with_mode(path, resolve_audio_output_mode())
    if cmd is None and player_name.endswith("(unavailable)"):
        logger.warning("[playback] %s", player_name)
    return (cmd, player_name)


def play_audio_file_interruptible(path: str | Path) -> PlaybackHandle | None:
    """
    Start playback in a subprocess. Returns a handle with is_running() and stop() for barge-in.
    Returns None if no player (e.g. AUDIO_OUTPUT_MODE=print or player unavailable).
    Caller should call handle.stop() to interrupt playback.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Audio file not found: {path}")
    cmd, player_name = get_playback_command(path)
    if cmd is None:
        if _debug_enabled():
            mode = resolve_audio_output_mode()
            print(f"[playback] no player mode={mode} player_name={player_name}", flush=True)
        return None
    if _debug_enabled():
        mode = resolve_audio_output_mode()
        binary = cmd[0] if cmd else player_name
        print(f"[playback] mode={mode} binary={binary} path={path}", flush=True)
    logger.debug("[playback] player=%s path=%s", player_name, path)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise RuntimeError(_NO_PLAYER_MSG) from None
    return PlaybackHandle(proc)


def play_audio_file(path: str | Path, timeout: int = 120) -> None:
    """
    Play audio file using platform-appropriate player. Blocks until playback completes or timeout.
    Uses play_audio_file_interruptible internally; single playback mechanism for ambient and non-ambient.
    Raises FileNotFoundError if file does not exist.
    Raises RuntimeError if no player available (except when AUDIO_OUTPUT_MODE=print).
    """
    path = Path(path)
    handle = play_audio_file_interruptible(path)
    if handle is None:
        if resolve_audio_output_mode() == "print":
            logger.debug("[playback] AUDIO_OUTPUT_MODE=print, skipping playback")
            return
        raise RuntimeError(_NO_PLAYER_MSG)
    deadline = time.monotonic() + timeout
    while handle.is_running() and time.monotonic() < deadline:
        time.sleep(0.05)
    if handle.is_running():
        handle.stop()


def get_playback_command_for_popen(path: str | Path) -> Tuple[list[str] | None, str]:
    """Same as get_playback_command; for use when caller will Popen (e.g. barge-in stop)."""
    return get_playback_command(path)
