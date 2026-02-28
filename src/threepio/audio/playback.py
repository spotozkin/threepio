"""Audio playback: re-export from threepio.speech.playback (canonical). Use threepio.speech.playback for new code."""

from __future__ import annotations

from threepio.speech.playback import (
    NO_PLAYER_MESSAGE,
    PlaybackHandle,
    get_audio_output_mode,
    get_resolved_playback_binary,
    play_audio_file,
    play_audio_file_interruptible,
    play_file,
    resolve_audio_output_mode,
    resolve_playback_mode,
    resolve_player,
    resolve_player_binary,
    stop_playback,
)

__all__ = [
    "NO_PLAYER_MESSAGE",
    "PlaybackHandle",
    "get_audio_output_mode",
    "get_resolved_playback_binary",
    "play_audio_file",
    "play_audio_file_interruptible",
    "play_file",
    "resolve_audio_output_mode",
    "resolve_playback_mode",
    "resolve_player",
    "resolve_player_binary",
    "stop_playback",
]
