"""Cross-platform audio playback via threepio.speech.playback."""

from pathlib import Path

from threepio.speech.playback import play_file, resolve_player, resolve_playback_mode

__all__ = ["play_audio", "resolve_player", "resolve_playback_mode"]


def play_audio(path: str | Path) -> None:
    """Play audio file using platform-appropriate player (afplay on macOS, ffplay/aplay/mpg123 on Linux).
    Blocks until playback completes. Respects AUDIO_OUTPUT_MODE (auto, afplay, ffplay, aplay, mpg123, print).
    Raises FileNotFoundError if file does not exist.
    Raises RuntimeError if no player available or playback fails.
    """
    play_file(path)
