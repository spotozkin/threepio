"""Coqui XTTS provider for voice-cloned TTS.

Requires: pip install TTS (typically in .venv-tts)
Run: source .venv-tts/bin/activate
     PROVIDER_TTS=xtts XTTS_REFERENCE_WAV=data/voice/processed/c3po_sam/reference.wav python -m threepio
"""

import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from threepio.speech.tts.base import BaseTTS

if TYPE_CHECKING:
    from threepio.io.speaker import SpeakerOutput
    from threepio.speech.rvc.rvc_converter import RVCConverter

logger = logging.getLogger(__name__)


class XTTSTTS(BaseTTS):
    """Coqui XTTS: voice-cloned synthesis via reference WAV."""

    def __init__(
        self,
        reference_wav: str | Path,
        model: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        language: str = "en",
        device: str = "cpu",
        speaker: "SpeakerOutput | None" = None,
        rvc_converter: "RVCConverter | None" = None,
    ) -> None:
        ref_path = Path(reference_wav).resolve()
        if not ref_path.exists():
            raise FileNotFoundError(f"XTTS reference WAV not found: {ref_path}")
        self._reference_wav = str(ref_path)
        self._model = model
        self._language = language
        self._device = device
        self._speaker = speaker
        self._rvc_converter = rvc_converter
        self._tts = None
        self._load_model()

    def _load_model(self) -> None:
        """Load Coqui TTS model once."""
        import torch

        # PyTorch 2.6+ defaults weights_only=True; Coqui XTTS checkpoints use custom
        # classes not in the safe-globals allowlist. Patch torch.load for model load only.
        _orig_torch_load = torch.load

        def _patched_torch_load(*args, **kwargs):  # noqa: N802
            kwargs.setdefault("weights_only", False)
            return _orig_torch_load(*args, **kwargs)

        torch.load = _patched_torch_load
        try:
            try:
                from TTS.tts.configs.xtts_config import XttsConfig
                from TTS.tts.models.xtts import XttsAudioConfig

                torch.serialization.add_safe_globals([XttsConfig, XttsAudioConfig])
            except Exception:
                pass

            from TTS.api import TTS

            logger.info("[XTTS] Loading model %s on %s", self._model, self._device)
            self._tts = TTS(self._model).to(self._device)
        finally:
            torch.load = _orig_torch_load

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to WAV bytes."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        try:
            self.synthesize_to_file(text, out_path)
            audio_bytes = Path(out_path).read_bytes()
            if self._rvc_converter:
                try:
                    audio_bytes = self._rvc_converter.convert_wav_bytes(audio_bytes)
                except Exception as e:
                    logger.warning("[XTTS] RVC conversion failed, using original audio: %s", e)
            return audio_bytes
        finally:
            Path(out_path).unlink(missing_ok=True)

    def synthesize_to_file(self, text: str, out_path: str) -> str:
        """Synthesize text to a WAV file. Returns the output path."""
        self._tts.tts_to_file(
            text=text,
            speaker_wav=self._reference_wav,
            language=self._language,
            file_path=out_path,
        )
        return out_path

    def speak(self, text: str) -> None:
        """Synthesize and play (or print if no speaker)."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            out_path = f.name
        try:
            self.synthesize_to_file(text, out_path)
            audio_bytes = Path(out_path).read_bytes()
            if self._rvc_converter:
                try:
                    audio_bytes = self._rvc_converter.convert_wav_bytes(audio_bytes)
                except Exception as e:
                    logger.warning("[XTTS] RVC conversion failed, using original audio: %s", e)
            if self._speaker:
                self._speaker.play(audio_bytes, format="wav")
            else:
                logger.debug("[XTTS] Skipping playback (AUDIO_OUTPUT_MODE=print or no player)")
                print(f"[TTS] {text} (no speaker)")
        finally:
            Path(out_path).unlink(missing_ok=True)

    def stop_playback(self) -> None:
        """Stop current playback for barge-in."""
        if self._speaker and hasattr(self._speaker, "stop"):
            self._speaker.stop()
