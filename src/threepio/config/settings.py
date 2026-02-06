"""Pydantic settings loaded from environment."""

import platform
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from threepio.config.env_loader import _should_load_dotenv


class Settings(BaseSettings):
    """Application settings from env with defaults."""

    model_config = SettingsConfigDict(
        env_file=".env" if _should_load_dotenv() else None,
        env_file_encoding="utf-8",
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
    PROVIDER_TTS: Literal["mock", "openai", "local_voice", "piper", "gtts"] = Field(
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
    AUDIO_OUTPUT_MODE: Literal["print", "play"] = Field(
        default="play" if platform.system() == "Darwin" else "print",
        description="'play' plays audio (mac: afplay), 'print' only prints",
    )

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


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
