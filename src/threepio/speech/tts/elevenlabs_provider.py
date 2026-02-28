"""ElevenLabs TTS provider using the official SDK.

Requires: pip install elevenlabs>=2.34.0
Run: PROVIDER_TTS=elevenlabs ELEVENLABS_API_KEY=... ELEVENLABS_VOICE_ID=... python -m threepio

Output format is configurable via ELEVENLABS_OUTPUT_FORMAT. Use mp3_44100_128 for streaming (default).
ELEVENLABS_STREAMING=1 (default) uses /stream; ELEVENLABS_STREAMING=0 or wav_* format uses non-streaming for best quality.
WAV and mp3_44100_320 require non-streaming; PCM formats require Pro tier.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import time
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from threepio.speech.tts.base import BaseTTS

# Voice setting defaults when env is unset (use ElevenLabs API defaults; don't override)
DEFAULT_SPEED = 1.0

if TYPE_CHECKING:
    from threepio.io.speaker import SpeakerOutput

logger = logging.getLogger(__name__)

# ElevenLabs format patterns: pcm_44100, wav_24000, mp3_44100_128
PCM_FORMAT_RE = re.compile(r"^pcm_(\d+)$")
WAV_FORMAT_RE = re.compile(r"^wav_(\d+)$")
MP3_FORMAT_RE = re.compile(r"^mp3_\d+_\d+$")

DEFAULT_OUTPUT_FORMAT = "mp3_44100_128"  # WAV not supported for streaming; use mp3 for streaming
NCHANNELS = 1
SAMPWIDTH = 2  # 16-bit
MIN_SYNTHESIZE_BYTES = 128  # Reject placeholder / null output; no silent fallback


class ElevenLabsConfigError(Exception):
    """Raised when ElevenLabs config (API key, voice ID) is invalid or missing."""


class ElevenLabsAPIError(Exception):
    """Raised when ElevenLabs API call fails."""


def _format_api_error(e: BaseException) -> str:
    """Build detailed error message from API exception."""
    parts = [str(e)]
    status_code = getattr(e, "status_code", None)
    body = getattr(e, "body", None)
    if status_code is not None:
        parts.append(f"status_code: {status_code}")
    if body is not None:
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        parts.append(f"body: {body}")
    # Add helpful hint for output_format_not_allowed
    if status_code == 403 and body:
        body_str = json.dumps(body) if isinstance(body, dict) else str(body)
        if "output_format_not_allowed" in body_str or "pcm" in body_str.lower():
            parts.append(
                "Your plan may not allow PCM. Try ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128 "
                "(or wav_24000 if your plan supports it). afplay plays MP3 directly."
            )
    return "; ".join(parts)


def _parse_pcm_framerate(output_format: str) -> int:
    """Extract sample rate from pcm_XXXX format."""
    m = PCM_FORMAT_RE.match(output_format)
    if m:
        return int(m.group(1))
    return 44100


def _parse_wav_framerate(output_format: str) -> int:
    """Extract sample rate from wav_XXXX format."""
    m = WAV_FORMAT_RE.match(output_format)
    if m:
        return int(m.group(1))
    return 44100


def _debug_enabled() -> bool:
    """True if THREEPIO_DEBUG is truthy (1, true, yes, on)."""
    v = os.environ.get("THREEPIO_DEBUG", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _bool_env(key: str, default: bool) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def parse_float(value: str | None) -> float | None:
    """Parse string to float. Returns None if missing, empty, or invalid. No percent interpretation (caller must provide 0..1)."""
    if value is None or not str(value).strip():
        return None
    try:
        return float(value.strip())
    except (ValueError, TypeError):
        return None


def parse_bool(value: str | None, default: bool = True) -> bool:
    """Parse string to bool. Returns default if missing or empty. Accepts 1/0, true/false, yes/no."""
    if value is None or not str(value).strip():
        return default
    lower = str(value).strip().lower()
    if lower in ("1", "true", "yes", "on"):
        return True
    if lower in ("0", "false", "no", "off"):
        return False
    return default


# Website "Best Quality" parity: explicit values, no optimize_streaming_latency
BEST_QUALITY_MODEL = "eleven_multilingual_v2"
BEST_QUALITY_OUTPUT_FORMAT = "mp3_44100_128"
BEST_QUALITY_VOICE = {
    "stability": 0.23,
    "similarity_boost": 0.75,
    "style": 0.08,
    "speed": 1.0,
    "use_speaker_boost": True,
}


@dataclass
class ElevenLabsConfig:
    """ElevenLabs config. Best Quality parity: model_id, output_format, voice_settings fixed."""

    api_key: str
    voice_id: str
    model_id: str = BEST_QUALITY_MODEL
    output_format: str = BEST_QUALITY_OUTPUT_FORMAT
    use_streaming: bool = True
    stability: float = 0.23
    similarity_boost: float = 0.75
    style: float = 0.08
    use_speaker_boost: bool = True
    speed: float = DEFAULT_SPEED

    @classmethod
    def from_env(cls) -> "ElevenLabsConfig":
        api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "").strip()
        if not api_key:
            raise ElevenLabsConfigError(
                "ELEVENLABS_API_KEY is required. Set it in .env or export ELEVENLABS_API_KEY=..."
            )
        if not voice_id:
            raise ElevenLabsConfigError(
                "ELEVENLABS_VOICE_ID is required. Get your voice ID from https://elevenlabs.io/app/voice-lab"
            )
        # Best Quality parity: locked to website settings
        model_id = BEST_QUALITY_MODEL
        output_format = BEST_QUALITY_OUTPUT_FORMAT
        # ELEVENLABS_STREAMING (default 1); fall back to ELEVENLABS_USE_STREAMING for backward compat
        streaming_requested = (
            _bool_env("ELEVENLABS_STREAMING", True)
            if "ELEVENLABS_STREAMING" in os.environ
            else _bool_env("ELEVENLABS_USE_STREAMING", True)
        )
        # WAV not supported for streaming; use non-streaming when STREAMING=0 or output_format is wav_*
        use_streaming = streaming_requested and not output_format.lower().startswith("wav_")
        # Voice settings: Best Quality parity (fixed)
        return cls(
            api_key=api_key,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            use_streaming=use_streaming,
            stability=BEST_QUALITY_VOICE["stability"],
            similarity_boost=BEST_QUALITY_VOICE["similarity_boost"],
            style=BEST_QUALITY_VOICE["style"],
            use_speaker_boost=BEST_QUALITY_VOICE["use_speaker_boost"],
            speed=BEST_QUALITY_VOICE["speed"],
        )

    def is_pcm(self) -> bool:
        return bool(PCM_FORMAT_RE.match(self.output_format))

    def is_wav(self) -> bool:
        return bool(WAV_FORMAT_RE.match(self.output_format))

    def is_mp3(self) -> bool:
        return bool(MP3_FORMAT_RE.match(self.output_format))


class ElevenLabsTTS(BaseTTS):
    """ElevenLabs TTS: custom voice with low latency via streaming."""

    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model_id: str = "eleven_multilingual_v2",
        output_format: str = DEFAULT_OUTPUT_FORMAT,
        use_streaming: bool = True,
        stability: Optional[float] = None,
        similarity_boost: Optional[float] = None,
        style: Optional[float] = None,
        use_speaker_boost: bool = False,
        speed: float = DEFAULT_SPEED,
        speaker: "SpeakerOutput | None" = None,
    ) -> None:
        self._config = ElevenLabsConfig(
            api_key=api_key,
            voice_id=voice_id,
            model_id=model_id,
            output_format=output_format,
            use_streaming=use_streaming,
            stability=stability,
            similarity_boost=similarity_boost,
            style=style,
            use_speaker_boost=use_speaker_boost,
            speed=speed,
        )
        self._speaker = speaker
        self._client = None
        self._playback_handle = None  # PlaybackHandle from speech.playback for stop_playback()

    def _get_client(self):
        """Lazy-init client to defer import and API key validation."""
        if self._client is None:
            try:
                from elevenlabs import ElevenLabs
            except ImportError as e:
                raise ElevenLabsConfigError(
                    "elevenlabs package not installed. Run: pip install elevenlabs>=2.34.0"
                ) from e
            self._client = ElevenLabs(api_key=self._config.api_key)
        return self._client

    def _build_voice_settings(self) -> "VoiceSettings":
        """Build VoiceSettings for website parity: always include speed (e.g. 1.0)."""
        from elevenlabs import VoiceSettings

        return VoiceSettings(
            stability=self._config.stability,
            similarity_boost=self._config.similarity_boost,
            style=self._config.style,
            speed=self._config.speed,
            use_speaker_boost=self._config.use_speaker_boost,
        )

    def _voice_settings_for_debug(self) -> dict:
        """Voice_settings dict as sent in API request, for debug logging (always includes speed)."""
        return {
            "stability": self._config.stability,
            "similarity_boost": self._config.similarity_boost,
            "style": self._config.style,
            "speed": self._config.speed,
            "use_speaker_boost": self._config.use_speaker_boost,
        }

    def _payload_for_debug(self, text: str) -> dict:
        """Build a dict of request payload fields for debug logging."""
        text_preview = text[:80] + "..." if len(text) > 80 else text
        vs = self._voice_settings_for_debug()
        return {
            "mode": "streaming" if self._config.use_streaming else "non_streaming",
            "voice_id": self._config.voice_id,
            "text": text_preview,
            "model_id": self._config.model_id,
            "output_format": self._config.output_format,
            "apply_text_normalization": "auto",
            "voice_settings": vs,
            "optimize_streaming_latency": "NOT_PASSED",  # Best Quality: never send this
        }

    def _build_request_kwargs(self, text: str) -> dict:
        """Build kwargs passed to ElevenLabs API. Used for parity validation."""
        voice_settings = self._build_voice_settings()
        return {
            "voice_id": self._config.voice_id,
            "text": text,
            "model_id": self._config.model_id,
            "output_format": self._config.output_format,
            "voice_settings": voice_settings,
            "apply_text_normalization": "auto",
        }

    def _fetch_audio_bytes(self, text: str) -> bytes:
        """Call API and return raw audio bytes (format from config). Caller handles file writing."""
        if not text or not text.strip():
            raise ValueError("Text cannot be empty")
        text = text.strip()
        client = self._get_client()
        voice_settings = self._build_voice_settings()
        if _debug_enabled():
            payload = self._payload_for_debug(text)
            endpoint = "stream" if self._config.use_streaming else "non-stream"
            base_url = "https://api.elevenlabs.io/v1/text-to-speech"
            full_endpoint = f"{base_url}/{{voice_id}}" + ("/stream" if self._config.use_streaming else "")
            payload_safe = {k: v for k, v in payload.items() if k != "voice_id"}
            payload_safe["voice_id"] = "(redacted)"
            logger.debug(
                "[ElevenLabs] endpoint=%s payload=%s",
                full_endpoint,
                json.dumps(payload_safe, default=str),
            )
            print(
                f"[ElevenLabs] endpoint={endpoint} output_format={payload['output_format']} "
                f"model_id={payload['model_id']} apply_text_normalization={payload['apply_text_normalization']} "
                f"voice_settings={json.dumps(payload['voice_settings'])}",
                flush=True,
            )
        common_kw = dict(
            voice_id=self._config.voice_id,
            text=text,
            model_id=self._config.model_id,
            output_format=self._config.output_format,
            voice_settings=voice_settings,
            apply_text_normalization="auto",
        )
        try:
            if self._config.use_streaming:
                audio_iter = client.text_to_speech.stream(**common_kw)
            else:
                audio_iter = client.text_to_speech.convert(**common_kw)
        except Exception as e:
            raise ElevenLabsAPIError(_format_api_error(e)) from e
        chunks = []
        for chunk in audio_iter:
            if chunk and isinstance(chunk, bytes):
                chunks.append(chunk)
            elif hasattr(chunk, "data") and chunk.data:
                chunks.append(chunk.data)
        return b"".join(chunks)

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to raw audio bytes. Format from config (mp3/wav/pcm). No file writing."""
        audio = self._fetch_audio_bytes(text)
        if audio is None or len(audio) < MIN_SYNTHESIZE_BYTES:
            raise RuntimeError(
                f"ElevenLabs returned too little audio ({len(audio) if audio else 0} bytes). "
                f"Minimum {MIN_SYNTHESIZE_BYTES} bytes required. No silent fallback."
            )
        return audio

    def synthesize_to_file(self, text: str, out_path: str) -> str:
        """Synthesize text to an audio file. Returns the output path.

        Handles:
        - wav_*: stream bytes directly to .wav
        - pcm_*: wrap PCM into WAV via wave module
        - mp3_*: stream bytes to .mp3; if out_path is .wav, writes to sibling .mp3 and returns that path
        """
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        audio_data = self.synthesize(text)
        fmt = self._config.output_format

        def _log_result(path_str: str) -> None:
            if _debug_enabled():
                p = Path(path_str)
                size = p.stat().st_size if p.exists() else 0
                print(f"[ElevenLabs] result_path={path_str} size={size}", flush=True)

        if self._config.is_pcm():
            with wave.open(str(out), "wb") as wav:
                wav.setnchannels(NCHANNELS)
                wav.setsampwidth(SAMPWIDTH)
                wav.setframerate(_parse_pcm_framerate(fmt))
                wav.writeframes(audio_data)
            _log_result(str(out))
            return str(out)

        if self._config.is_wav():
            out_actual = out.with_suffix(".wav") if out.suffix.lower() != ".wav" else out
            out_actual.write_bytes(audio_data)
            _log_result(str(out_actual))
            return str(out_actual)

        # mp3_*
        if out.suffix.lower() == ".wav":
            # User requested .wav but we're using mp3
            mp3_path = out.with_suffix(".mp3")
            mp3_path.write_bytes(audio_data)
            logger.warning(
                "ELEVENLABS_OUTPUT_FORMAT=%s produces MP3; wrote %s instead of %s. "
                "Play with: afplay %s",
                fmt,
                mp3_path,
                out,
                mp3_path,
            )
            _log_result(str(mp3_path))
            return str(mp3_path)
        out_actual = out.with_suffix(".mp3") if out.suffix.lower() != ".mp3" else out
        out_actual.write_bytes(audio_data)
        _log_result(str(out_actual))
        return str(out_actual)

    def speak(self, text: str) -> None:
        """Synthesize and play using AUDIO_OUTPUT_MODE and shared speech.playback."""
        from threepio.config import get_settings
        from threepio.speech.playback import play_audio_file_interruptible

        settings = get_settings()
        mode = (getattr(settings, "AUDIO_OUTPUT_MODE", None) or "auto").strip().lower()
        if mode == "play":
            mode = "auto"
        if mode == "print":
            with tempfile.TemporaryDirectory() as tmpdir:
                out_path = Path(tmpdir) / ("tts.mp3" if self._config.is_mp3() else "tts.wav")
                self.synthesize_to_file(text, str(out_path))
            return
        with tempfile.TemporaryDirectory() as tmpdir:
            filename = "tts.mp3" if self._config.is_mp3() else "tts.wav"
            out_path = Path(tmpdir) / filename
            self.synthesize_to_file(text, str(out_path))
            handle = play_audio_file_interruptible(out_path)
            if handle is None:
                from threepio.speech.playback import NO_PLAYER_MESSAGE
                raise RuntimeError(NO_PLAYER_MESSAGE)
            self._playback_handle = handle
            try:
                deadline = time.monotonic() + 120
                while handle.is_running() and time.monotonic() < deadline:
                    time.sleep(0.05)
                if handle.is_running():
                    handle.stop()
            finally:
                self._playback_handle = None

    def stop_playback(self) -> None:
        """Stop current playback for barge-in."""
        if self._playback_handle is not None and self._playback_handle.is_running():
            self._playback_handle.stop()
            self._playback_handle = None
