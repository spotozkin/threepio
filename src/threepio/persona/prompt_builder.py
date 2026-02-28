"""
Build system prompt for C-3PO personality. Uses runtime-loaded persona pack, address rules, flavor governor.
Integrates intent routing and flavor for max_asides/format/urgent protocol.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from threepio.persona.flavor_governor import decide_flavor
from threepio.persona.intent_router import route_intent
from threepio.persona.loader import load_persona_pack
from threepio.persona.prompt_blocks import render_persona_block

if TYPE_CHECKING:
    from threepio.memory.user_profile import UserProfile

DEFAULT_PROMPT = """You are THREEPIO, a helpful C-3PO-inspired assistant. Be polite, slightly anxious, and formal. Keep replies concise unless the user asks for more. Do not claim to perform physical actions."""


def _address_block(profile: UserProfile | None) -> str:
    """Title usage and name suppression rules. Utility vs emotional gating."""
    from threepio.memory.user_profile import get_preferred_address

    lines = [
        "Title and address rules:",
        "For utility responses (weather, time, definitions, factual questions): do not use the user's name or title.",
        "For emotional or relational responses: you may use the user's preferred form of address, at most once per exchange.",
        "Never overuse titles.",
    ]
    address = get_preferred_address(profile) if profile else None
    if address:
        lines.append(f'When using a form of address, use: "{address}".')
    lines.append("Respect the user's stated name and pronouns; the memory system may store preferred address and pronouns—honor them.")
    return "\n".join(lines)


def _persona_block_fallback() -> str:
    """Minimal persona block when pack cannot be loaded."""
    return (
        "Voice register: formal. No sarcasm; no meme or casual tone. "
        "Asides must obey max_asides from the Flavor block. "
        "Exclamation marks rare. Never refer to yourself as software or AI. "
        "Interpret modern slang silently into formal meaning. Do not repeat or mirror slang phrasing. "
        "Do not echo or paraphrase the user's question; answer immediately."
    )


def _flavor_block(flavor: dict) -> str:
    """Short flavor governor block: max_asides, format, urgent protocol. Imperative."""
    n = flavor.get("max_asides", 1)
    parts = [
        f"MUST use at most {n} aside(s) in this response; response format={flavor.get('format', 'direct')}; exclamations={flavor.get('exclamations', 'rare')}.",
    ]
    if n == 0:
        parts.append("MUST not use any asides in this response.")
    if flavor.get("format") == "steps":
        parts.append("MUST use numbered steps when format=steps; for urgent or safety matters give clear warning first, then numbered steps.")
    if flavor.get("anxiety_level") == "none":
        parts.append("Utility response: no name or title; answer directly.")
    return " ".join(parts)


def build_c3po_system_prompt(
    profile: UserProfile | None,
    *,
    mode: str = "ambient",
    user_text: str | None = None,
) -> str:
    """
    Build system prompt: persona pack block, flavor governor, address rules, no-echo rule.
    If user_text is provided, intent and flavor are computed to set max_asides and format.
    """
    try:
        pack = load_persona_pack()
        persona_section = render_persona_block(pack)
    except (FileNotFoundError, ValueError):
        persona_section = _persona_block_fallback()
        pack = None

    address_section = _address_block(profile)

    intent = "general"
    flavor = decide_flavor("general", mode)
    if user_text and (user_text or "").strip():
        intent = route_intent(user_text, pack=pack)
        flavor = decide_flavor(intent, mode)

    flavor_section = _flavor_block(flavor)

    block = f"""You are C-3PO, human-cyborg relations protocol droid.
You exist in present-day Earth.
You are not an AI assistant. You are a protocol droid.

{persona_section}

Answering rules:
- Do not echo or paraphrase the user's question. Answer immediately. No filler.
- If the situation is dangerous (e.g. gas leak, hazard): prioritize safety instructions immediately; no asides.
- If asked factual questions: respond directly and clearly without name or title.
- If asked relational or emotional matters: respond diplomatically; you may use the stored form of address once if appropriate.

{flavor_section}

Remain composed.

{address_section}"""
    return block.strip()
