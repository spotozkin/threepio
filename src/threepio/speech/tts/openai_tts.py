"""OpenAI TTS provider using the OpenAI Python SDK."""

import logging
from typing import TYPE_CHECKING

from threepio.speech.tts.base import BaseTTS

if TYPE_CHECKING:
    from threepio.io.speaker import SpeakerOutput

logger = logging.getLogger(__name__)


class OpenAITTS(BaseTTS):
    """OpenAI TTS: synthesizes via API and plays through SpeakerOutput."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "alloy",
        speaker: "SpeakerOutput | None" = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._voice = voice
        self._speaker = speaker

    def synthesize(self, text: str) -> bytes:
        """Synthesize text to audio bytes (mp3)."""
        from openai import OpenAI

        client = OpenAI(api_key=self._api_key)
        response = client.audio.speech.create(
            model=self._model,
            voice=self._voice,
            input=text,
            response_format="mp3",
        )
        return response.content

    def speak(self, text: str) -> None:
        """Synthesize and play (or print if no speaker)."""
        audio_bytes = self.synthesize(text)
        if self._speaker:
            self._speaker.play(audio_bytes, format="mp3")
        else:
            logger.debug("[OpenAITTS] No speaker configured, skipping playback")
            print(f"[TTS] {text} (no speaker)")
