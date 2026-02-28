"""TTS provider factory. Respects PROVIDER_TTS. No silent fallback to mock."""

import logging
from pathlib import Path
from threepio.speech.tts.base import BaseTTS

logger = logging.getLogger(__name__)

ALLOWED_PROVIDER_TTS = ("mock", "openai", "elevenlabs", "retrieval", "xtts")


def _validate_synthesize(provider: BaseTTS) -> None:
    """Raise TypeError if provider does not have callable synthesize()."""
    meth = getattr(provider, "synthesize", None)
    if not callable(meth):
        raise TypeError(
            f"Provider {type(provider).__name__} has no callable synthesize() method. "
            "TTS providers must implement synthesize(text: str) -> bytes."
        )

_SYNTH_METHOD_NAMES = [
    "synthesize_to_file", "tts_to_file", "generate_to_file",
    "speak_to_file", "write_audio", "synthesize", "generate",
]

# Call signatures: (kwargs dict or None for positional)
_SYNTH_SIGNATURES = [
    lambda fn, t, o: fn(text=t, out_path=str(o)),
    lambda fn, t, o: fn(t, str(o)),
    lambda fn, t, o: fn(text=t, output_path=str(o)),
    lambda fn, t, o: fn(text=t, file_path=str(o)),
]


def synthesize_to_file(provider: BaseTTS, text: str, out_path: str) -> str | Path | None:
    """Call provider's synthesize method. Prefers direct synthesize_to_file if present.
    Returns str|Path|None. Raises AttributeError if no suitable method found.
    """
    out = Path(out_path)
    meth = getattr(provider, "synthesize_to_file", None)
    if callable(meth):
        result = meth(text, str(out_path))
        return result if result is not None else out
    for name in _SYNTH_METHOD_NAMES:
        meth = getattr(provider, name, None)
        if not callable(meth):
            continue
        for sig in _SYNTH_SIGNATURES:
            try:
                result = sig(meth, text, out_path)
                return result if result is not None else out
            except TypeError:
                continue
    raise AttributeError(
        f"Provider {type(provider).__name__} has no recognized synthesize method. "
        "Expected one of: synthesize_to_file, tts_to_file, generate_to_file, "
        "speak_to_file, write_audio, synthesize, generate. "
        "Please provide provider class name and method name."
    )


def get_tts_provider() -> BaseTTS:
    """Return TTS provider based on PROVIDER_TTS. Raises ValueError if missing/invalid; no silent fallback to mock."""
    from threepio.config import get_settings

    settings = get_settings()
    provider_name = (settings.PROVIDER_TTS or "").strip().lower()
    # Normalize aliases
    if provider_name in ("11labs", "eleven-labs"):
        provider_name = "elevenlabs"

    if not provider_name or provider_name not in ALLOWED_PROVIDER_TTS:
        raise ValueError(
            f"PROVIDER_TTS must be one of: {', '.join(ALLOWED_PROVIDER_TTS)} (got {provider_name!r}). "
            "Set PROVIDER_TTS in .env or .envrc."
        )

    if provider_name == "mock":
        from threepio.speech.tts.mock_tts import MockTTS
        provider = MockTTS()
        _validate_synthesize(provider)
        logger.info("[TTS] provider=mock reference=none")
        return provider

    if provider_name == "retrieval":
        dataset_dir_str = getattr(settings, "LOCAL_VOICE_DATASET_DIR", "") or ""
        dataset_dir = Path(dataset_dir_str).resolve()
        if not dataset_dir.exists():
            raise ValueError(
                f"PROVIDER_TTS=retrieval but LOCAL_VOICE_DATASET_DIR={dataset_dir} does not exist."
            )
        from threepio.speech.tts.retrieval_tts import RetrievalTTS
        provider = RetrievalTTS(dataset_dir)
        _validate_synthesize(provider)
        logger.info("[TTS] provider=retrieval reference=%s", dataset_dir)
        return provider

    if provider_name == "openai":
        api_key = (getattr(settings, "OPENAI_API_KEY", None) or "").strip()
        if not api_key:
            raise ValueError("PROVIDER_TTS=openai requires OPENAI_API_KEY. Set it in .env or .envrc.")
        from threepio.io.speaker import MacSpeakerOutput, MockSpeakerOutput
        from threepio.speech.tts.openai_tts import OpenAITTS
        audio_mode = getattr(settings, "AUDIO_OUTPUT_MODE", "auto") or "auto"
        speaker = (
            MacSpeakerOutput()
            if audio_mode != "print"
            else MockSpeakerOutput()
        )
        provider = OpenAITTS(
            api_key=api_key,
            model=getattr(settings, "TTS_MODEL", "tts-1"),
            voice=getattr(settings, "TTS_VOICE", "alloy"),
            speaker=speaker,
        )
        _validate_synthesize(provider)
        logger.info("[TTS] provider=openai reference=none")
        return provider

    if provider_name == "elevenlabs":
        from threepio.speech.tts.elevenlabs_provider import (
            ElevenLabsConfig,
            ElevenLabsConfigError,
            ElevenLabsTTS,
        )
        try:
            cfg = ElevenLabsConfig.from_env()
        except ElevenLabsConfigError as e:
            raise ValueError(f"PROVIDER_TTS=elevenlabs config error: {e}") from e
        provider = ElevenLabsTTS(
            api_key=cfg.api_key,
            voice_id=cfg.voice_id,
            model_id=cfg.model_id,
            output_format=cfg.output_format,
            use_streaming=cfg.use_streaming,
            stability=cfg.stability,
            similarity_boost=cfg.similarity_boost,
            style=cfg.style,
            use_speaker_boost=cfg.use_speaker_boost,
            speed=cfg.speed,
        )
        _validate_synthesize(provider)
        logger.info("[TTS] provider=elevenlabs reference=none")
        return provider

    if provider_name == "xtts":
        ref_str = getattr(settings, "XTTS_REFERENCE_WAV", "") or ""
        ref_path = Path(ref_str).resolve()
        if not ref_path.exists():
            raise ValueError(
                f"PROVIDER_TTS=xtts but XTTS_REFERENCE_WAV={ref_path} does not exist."
            )
        from threepio.io.speaker import MacSpeakerOutput, MockSpeakerOutput
        from threepio.speech.rvc.rvc_converter import get_rvc_converter_or_none
        from threepio.speech.tts.xtts_provider import XTTSTTS
        audio_mode = getattr(settings, "AUDIO_OUTPUT_MODE", "auto") or "auto"
        speaker = (
            MacSpeakerOutput()
            if audio_mode != "print"
            else MockSpeakerOutput()
        )
        rvc_converter = get_rvc_converter_or_none()
        provider = XTTSTTS(
            reference_wav=str(ref_path),
            model=getattr(settings, "XTTS_MODEL", "tts_models/multilingual/multi-dataset/xtts_v2"),
            language=getattr(settings, "XTTS_LANGUAGE", "en"),
            device=getattr(settings, "XTTS_DEVICE", "cuda"),
            speaker=speaker,
            rvc_converter=rvc_converter,
        )
        _validate_synthesize(provider)
        logger.info("[TTS] provider=xtts reference=%s rvc=%s", ref_path, rvc_converter is not None)
        return provider

    raise ValueError(f"PROVIDER_TTS={provider_name!r} not implemented.")
