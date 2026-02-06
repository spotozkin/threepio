"""Schema for voice dataset metadata."""

from pydantic import BaseModel, Field


class VoiceSampleRow(BaseModel):
    """Single row in metadata.csv: audio path and transcript."""

    audio_path: str = Field(..., description="Path to wav file (relative to metadata)")
    transcript: str = Field(..., min_length=1, description="Utterance text")
    duration_sec: float | None = Field(default=None, description="Duration in seconds (optional)")


def parse_metadata_line(line: str) -> VoiceSampleRow | None:
    """Parse a CSV line into VoiceSampleRow. Returns None for empty/invalid lines."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split("|", 2)
    if len(parts) < 2:
        return None
    return VoiceSampleRow(
        audio_path=parts[0].strip(),
        transcript=parts[1].strip(),
        duration_sec=float(parts[2].strip()) if len(parts) > 2 and parts[2].strip() else None,
    )
