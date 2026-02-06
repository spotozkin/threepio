"""Speaker output abstraction for audio playback."""

import logging
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)


class SpeakerOutput(ABC):
    """Abstract speaker/audio output."""

    @abstractmethod
    def play(self, audio_bytes: bytes, format: str = "mp3") -> None:
        """Play audio bytes. Format: mp3, wav, etc."""
        ...


class MockSpeakerOutput(SpeakerOutput):
    """Mock: prints only, no audio playback."""

    def play(self, audio_bytes: bytes, format: str = "mp3") -> None:
        """Print that audio would play (length in bytes)."""
        logger.debug("[Speaker] Would play %d bytes (%s)", len(audio_bytes), format)
        print(f"[TTS] (audio {len(audio_bytes)} bytes, format={format})")


class MacSpeakerOutput(SpeakerOutput):
    """macOS: write to temp file and play via afplay."""

    def play(self, audio_bytes: bytes, format: str = "mp3") -> None:
        """Write bytes to temp file and run afplay."""
        suffix = f".{format}" if not format.startswith(".") else format
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            path = Path(f.name)
            f.write(audio_bytes)
        try:
            logger.debug("[Speaker] Playing %s via afplay", path)
            subprocess.run(
                ["afplay", str(path)],
                check=True,
                capture_output=True,
                timeout=120,
            )
        except subprocess.CalledProcessError as e:
            logger.error("[Speaker] afplay failed: %s", e)
            raise
        except FileNotFoundError:
            logger.error("[Speaker] afplay not found (macOS only)")
            raise
        finally:
            path.unlink(missing_ok=True)
