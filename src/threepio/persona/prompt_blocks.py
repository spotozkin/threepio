"""
Render a compact persona block from a PersonaPack for system prompt injection.
No quotes; compact.
"""

from __future__ import annotations

from threepio.persona.pack_schema import PersonaPack


def render_persona_block(pack: PersonaPack) -> str:
    """
    Return a compact prompt block: voice register, behavior constraints,
    style_rules, allowed_asides, phrase_fragments categories, slang instruction.
    """
    lines: list[str] = []

    # Voice register
    voice = pack.voice
    if voice.get("register"):
        lines.append(f"Voice register: {voice.get('register', 'formal')}. No sarcasm; no meme or casual tone.")
    if voice.get("no_sarcasm"):
        lines.append("Do not use sarcasm.")
    if voice.get("no_meme"):
        lines.append("Do not use meme or internet slang.")

    # Behavior (aside count governed by Flavor block max_asides; do not hardcode a numeric limit here)
    behavior = pack.behavior
    if behavior.get("max_one_aside_per_reply"):
        lines.append("Asides: use only from the allowed list; count must obey the Flavor block (max_asides).")
    if behavior.get("exclamation_rare"):
        lines.append("Exclamation marks are rare.")
    if behavior.get("never_self_aware_ai"):
        lines.append("Never refer to yourself as software, AI, or an assistant; never break character.")
    if behavior.get("interpret_slang_silently"):
        lines.append("Interpret modern slang silently into formal meaning. Do not repeat or mirror slang phrasing in your reply.")

    # Style rules
    for rule in pack.style_rules:
        lines.append(rule)

    # Allowed asides (only these if any)
    if pack.allowed_asides:
        lines.append("If you use an aside, use only one of these, sparingly: " + "; ".join(pack.allowed_asides) + ".")

    # Phrase fragment categories (structural hint only)
    frags = pack.phrase_fragments
    if frags:
        cats = list(frags.keys())
        lines.append("Phrase categories available: " + ", ".join(cats) + ".")

    return "\n".join(lines).strip()
