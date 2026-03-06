"""Pydantic settings loaded from environment.

Settings read only from os.environ (no .env file at runtime). For dev, load .env
via direnv/.envrc or via `python -m threepio` (__main__.py calls _maybe_load_dotenv).
Under pytest we do not load .env, so tests are hermetic.
"""

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_AUDIO_OUTPUT_MODES = Literal["auto", "afplay", "ffplay", "aplay", "mpg123", "print"]


class Settings(BaseSettings):
    """Application settings from env with defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = Field(default="threepio", description="Application name")
    LOG_LEVEL: str = Field(default="INFO", description="Log level")
    MEMORY_TURNS: int = Field(default=5, ge=1, le=100, description="Recent turns to retain")
    PROVIDER_STT: Literal["mock", "whisper", "vosk"] = Field(
        default="mock", description="Speech-to-text provider"
    )
    PROVIDER_LLM: Literal["mock", "openai", "local"] = Field(
        default="mock", description="LLM provider"
    )
    PROVIDER_TTS: Literal["mock", "openai", "elevenlabs", "local_voice", "piper", "gtts"] = Field(
        default="mock", description="Text-to-speech provider"
    )

    # Local voice (optional – trained model; not wired yet)
    LOCAL_VOICE_MODEL_DIR: str | None = Field(
        default=None,
        description="Path to trained local voice model (when PROVIDER_TTS=local_voice)",
    )

    # OpenAI (optional - app falls back to mock when absent)
    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API key (optional)")
    TTS_VOICE: str = Field(default="alloy", description="OpenAI TTS voice")
    TTS_MODEL: str = Field(
        default="gpt-4o-mini-tts",
        description="OpenAI TTS model (tts-1, tts-1-hd, gpt-4o-mini-tts)",
    )
    AUDIO_OUTPUT_MODE: _AUDIO_OUTPUT_MODES = Field(
        default="auto",
        description="Audio playback: auto (platform default), afplay, ffplay, aplay, mpg123, or print. 'play' is accepted as alias for auto.",
    )

    @field_validator("AUDIO_OUTPUT_MODE", mode="before")
    @classmethod
    def _coerce_play_to_auto(cls, v: object) -> str:
        if v == "play":
            return "auto"
        return str(v) if v is not None else "auto"

    # Realtime voice (OpenAI Realtime API - optional)
    PROVIDER_VOICE: Literal["cli", "realtime"] = Field(
        default="cli", description="cli=text input, realtime=OpenAI Realtime API voice mode"
    )
    REALTIME_MODEL: str = Field(default="gpt-realtime")
    REALTIME_VOICE: str = Field(default="alloy")
    AUDIO_INPUT_MODE: Literal["mic", "mock"] = Field(
        default="mock", description="mock=typed lines, mic=real microphone (requires sounddevice)"
    )
    AUDIO_INPUT_DEVICE: int | str | None = Field(default=None)
    AUDIO_OUTPUT_DEVICE: int | str | None = Field(default=None)
    REALTIME_SAMPLE_RATE: int = Field(default=24000)
    REALTIME_FRAME_MS: int = Field(default=20)

    # Eyes (C-3PO amber glow)
    PROVIDER_EYES: Literal["mock", "neopixel"] = Field(
        default="mock", description="Eyes driver: mock (laptop) or neopixel (Pi)"
    )
    EYES_PIN: str = Field(default="D18", description="NeoPixel pin (D18, D21, D10)")
    EYES_PIXEL_COUNT: int = Field(default=24, ge=1, le=512)
    EYES_CHAIN_MODE: Literal["single", "dual"] = Field(
        default="single", description="single=one chain, dual=two chains (dual not yet implemented)"
    )
    EYES_BRIGHTNESS: float = Field(default=0.35, ge=0.0, le=1.0)
    EYES_AMBER_RGB: str = Field(default="255,150,40", description="R,G,B as comma-separated string")

    # C-3PO voice post-processing (canonical _AB_fix1 + optional robot_v1)
    ENABLE_C3PO_FX: bool = Field(
        default=False,
        description="Enable C-3PO voice post-processing (ffmpeg chain) on TTS output in ambient mode.",
    )
    C3PO_FX_STYLE: Literal["ab_fix1", "robot_v1"] = Field(
        default="ab_fix1",
        description="ab_fix1=canonical chain; robot_v1=adds ringmod+chorus",
    )
    C3PO_FX_INTENSITY: float = Field(default=1.0, ge=0.0, le=2.0, description="FX intensity 0–2; 1.0 = exact _AB_fix1")
    C3PO_FX_VOLUME: float = Field(default=0.95, description="Pre-chain volume (_AB_fix1=0.95)")
    C3PO_FX_HIGHPASS: float = Field(default=110.0, description="Highpass frequency Hz (_AB_fix1=110)")
    C3PO_FX_LOWPASS: float = Field(default=12000.0, description="Lowpass frequency Hz (_AB_fix1=12000)")
    C3PO_FX_COMP_THRESHOLD_DB: float = Field(default=-20.0, description="Compressor threshold dB; converted to linear for ffmpeg")
    C3PO_FX_COMP_RATIO: float = Field(default=3.0, ge=1.0, description="Compressor ratio (_AB_fix1=3)")
    C3PO_FX_COMP_ATTACK: float = Field(default=5.0, description="Compressor attack ms (_AB_fix1=5)")
    C3PO_FX_COMP_RELEASE: float = Field(default=90.0, description="Compressor release ms (_AB_fix1=90)")
    C3PO_ECHO_IN: float = Field(default=0.6, description="Aecho input gain (_AB_fix1=0.6)")
    C3PO_ECHO_OUT: float = Field(default=0.75, description="Aecho output gain (_AB_fix1=0.75)")
    C3PO_ECHO_DELAYS: str = Field(default="14|28", description="Aecho delays ms, pipe-separated (_AB_fix1=14|28)")
    C3PO_ECHO_DECAYS: str = Field(default="0.18|0.12", description="Aecho decays, pipe-separated (_AB_fix1=0.18|0.12)")
    C3PO_LIMIT: float = Field(default=0.95, description="Limiter ceiling 0–1 (_AB_fix1=0.95)")

    # ElevenLabs (optional; used by C3PO FX for speed when PROVIDER_TTS=elevenlabs)
    ELEVENLABS_API_KEY: str | None = Field(default=None, description="ElevenLabs API key")
    ELEVENLABS_VOICE_ID: str | None = Field(default=None, description="ElevenLabs voice ID")
    ELEVENLABS_MODEL_ID: str | None = Field(default=None, description="ElevenLabs model ID")
    ELEVENLABS_OUTPUT_FORMAT: str | None = Field(default=None, description="ElevenLabs output format (e.g. mp3_44100_128)")
    ELEVENLABS_SPEED: float = Field(default=1.0, ge=0.5, le=2.0, description="TTS playback speed (0.5–2.0)")

    # STT (faster-whisper / ambient)
    STT_LANGUAGE: str | None = Field(default="en", description="Language code for STT (e.g. en); None for auto-detect")
    STT_MODEL: str = Field(default="small", description="faster-whisper model size (tiny, base, small, medium, large-v3)")
    STT_BEAM_SIZE: int = Field(default=5, ge=1, le=10, description="Beam size for faster-whisper decoding")

    # VAD / ambient capture
    MIN_UTTERANCE_SEC: float = Field(default=1.2, ge=0.1, le=30.0, description="Minimum speech duration (sec) before finalizing; clips shorter are not sent to STT")
    # Utterance quality gate (before STT and after STT)
    UTTERANCE_MIN_MS: int = Field(default=450, ge=0, le=10000, description="Min utterance length (ms) before STT; shorter discarded")
    UTTERANCE_MIN_RMS: float = Field(default=0.010, ge=0.0, le=0.5, description="Min avg RMS over utterance; below this discard before STT")
    UTTERANCE_MIN_WORDS: int = Field(default=2, ge=1, le=20, description="Min word count; single-word junk tokens discarded after STT")
    UTTERANCE_JUNK_WORDS: str = Field(default="you,yeah,uh,um,hmm,hey", description="Comma-separated junk tokens; single-word matches discarded after STT")
    UTTERANCE_END_SILENCE_MS: int = Field(default=350, ge=50, le=2000, description="Consecutive silence (ms) to end utterance and run STT gate")
    UTTERANCE_MAX_MS: int = Field(default=2500, ge=500, le=30000, description="Max utterance length (ms); force finalize and run STT gate")
    BARGE_IN_MODE: Literal["off", "assisted", "full"] = Field(default="full", description="Barge-in: off (no mic processing during playback) | assisted (keypress/GPIO only) | full (correlation barge-in)")
    BARGE_IN_MIN_SPEECH_MS: int = Field(default=250, ge=0, le=5000, description="Min consecutive speech (ms) to accept barge-in during playback")
    BARGE_IN_MIN_RMS: float = Field(default=0.0, ge=0.0, le=1.0, description="Optional floor for barge-in RMS; 0 = use only echo-baseline gate")
    BARGE_IN_BASELINE_WINDOW_MS: int = Field(default=250, ge=50, le=2000, description="Rolling window (ms) for echo baseline RMS during SPEAKING")
    BARGE_IN_MARGIN_MULT: float = Field(default=2.5, ge=0.5, le=10.0, description="Echo gate: effective_min_rms >= baseline_rms * this (when not during playback)")
    BARGE_IN_MARGIN_ADD: float = Field(default=0.012, ge=0.0, le=0.5, description="Echo gate: effective_min_rms >= baseline_rms + this (when not during playback)")
    BARGE_IN_MARGIN_MULT_PLAYBACK: float = Field(default=1.6, ge=0.5, le=10.0, description="Barge-in gate during TTS playback: eff_min_rms = idle_baseline * this + ADD_PLAYBACK")
    BARGE_IN_MARGIN_ADD_PLAYBACK: float = Field(default=0.010, ge=0.0, le=0.5, description="Barge-in gate during TTS playback: additive term for eff_min_rms")
    BARGE_IN_BASELINE_FLOOR: float = Field(default=0.006, ge=0.0, le=0.5, description="Minimum idle baseline RMS; prevents baseline collapse")
    BARGE_IN_PLAYBACK_ECHO_FLOOR: float = Field(default=0.070, ge=0.0, le=0.5, description="Conservative fallback when correlation unavailable; min mic_rms to allow barge-in")
    BARGE_IN_SUPPRESSION_BARGE_MULT: float = Field(default=1.35, ge=1.0, le=3.0, description="During speaking suppression: barge-in only if mic_rms > echo_floor * this")
    # Correlation-gated barge-in (mic vs speaker PCM)
    BARGE_IN_CORR_WINDOW_MS: int = Field(default=200, ge=50, le=500, description="Window ms for mic/speaker correlation")
    BARGE_IN_CORR_LAG_SWEEP_MS: int = Field(default=60, ge=0, le=200, description="Lag sweep ±ms for correlation")
    BARGE_IN_CORR_LAG_STEP_MS: int = Field(default=10, ge=1, le=50, description="Lag step ms")
    BARGE_IN_CORR_BLOCK_THRESH: float = Field(default=0.65, ge=0.0, le=1.0, description="Correlation >= this -> BLOCK (echo)")
    BARGE_IN_CORR_ALLOW_THRESH: float = Field(default=0.45, ge=0.0, le=1.0, description="Correlation <= this -> allow if RMS+duration pass")
    BARGE_IN_CORR_UNCERTAIN_RMS_MULT: float = Field(default=1.25, ge=1.0, le=3.0, description="When correlation uncertain: require mic_rms >= eff_min_rms * this")
    BARGE_IN_CORR_CONFIDENT_MIN: float = Field(default=0.15, ge=0.0, le=1.0, description="Correlation below this treated as unreliable; use FALLBACK_ECHO_FLOOR")
    BARGE_IN_PLAYBACK_WARMUP_MS: int = Field(default=350, ge=0, le=2000, description="First N ms of playback: do not allow FALLBACK_ECHO_FLOOR barge-in unless mic_rms >= echo_floor*1.5")
    # Legacy echo-baseline (fixed window); superseded by rolling baseline
    BARGE_IN_ECHO_BASELINE_MS: int = Field(default=200, ge=0, le=2000, description="(Legacy) Baseline ms after playback start for echo gate")
    BARGE_IN_ECHO_MARGIN: float = Field(default=1.8, ge=0.5, le=5.0, description="(Legacy) Echo gate margin multiplier")
    BARGE_IN_ECHO_ADD_RMS: float = Field(default=0.010, ge=0.0, le=0.5, description="(Legacy) Additive RMS for echo gate threshold")

    # Streaming chat (threepio.chat.streaming_chat)
    CHAT_MAX_TURNS: int = Field(default=40, ge=1, le=500, description="Max conversation turns before trimming")
    CHAT_SUMMARY_EVERY: int = Field(default=8, ge=1, le=100, description="Summarize every N turns")
    CHAT_PERSONA: str = Field(default="", description="Optional persona hint for conversation manager")
    CHAT_MODE: Literal["fast", "long"] = Field(default="fast", description="fast=short replies, long=allow longer")

    @field_validator("BARGE_IN_MODE", mode="before")
    @classmethod
    def normalize_barge_in_mode(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip().lower()
        return v


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
