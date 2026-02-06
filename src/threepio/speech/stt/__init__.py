"""Speech-to-text providers."""

from threepio.speech.stt.base import BaseSTT
from threepio.speech.stt.mock_stt import MockSTT

__all__ = ["BaseSTT", "MockSTT"]
