"""Address gating: preferred address from profile and optional prefixing."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from threepio.memory.user_profile import UserProfile


def extract_speaker_address(profile: UserProfile | None) -> str | None:
    """Return preferred address from profile (uses user_profile.get_preferred_address)."""
    if profile is None:
        return None
    from threepio.memory.user_profile import get_preferred_address
    return get_preferred_address(profile)


def maybe_prefix_address(text: str, address: str | None, inject: bool) -> str:
    """If inject and address present and text doesn't start with it, prefix '{address}, {text}'."""
    if not inject or not address or not text:
        return text
    text = text.strip()
    if text.startswith(address):
        return text
    return f"{address}, {text}"
