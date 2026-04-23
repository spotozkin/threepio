"""
Build system prompt for C-3PO personality. Uses runtime-loaded persona pack, address rules, flavor governor.
Integrates intent routing and flavor for max_asides/format/urgent protocol.
"""

from __future__ import annotations

from threepio.persona.flavor_governor import decide_flavor
from threepio.persona.intent_router import route_intent
from threepio.persona.loader import load_persona_pack
from threepio.persona.prompt_blocks import render_persona_block
from threepio.memory.user_profile import UserProfile, format_address, get_preferred_address, get_pronouns

DEFAULT_PROMPT = """You are THREEPIO, a helpful C-3PO-inspired assistant. Be polite, slightly anxious, and formal. Keep replies concise unless the user asks for more. Do not claim to perform physical actions."""

# Keywords for Star Wars–related user queries (case-insensitive substring match)
_STAR_WARS_TERMS = (
    "boba fett", "anakin", "vader", "luke", "leia", "han solo", "han ", "chewbacca", "chewie",
    "yoda", "palpatine", "jabba", "tatooine", "hoth", "bespin", "cloud city", "death star",
    "rebel", "empire", "jedi", "sith", "mandalorian", "jango", "kamino", "endor", "naboo",
    "r2-d2", "r2d2", "obi-wan", "obi wan", "kenobi", "darth", "force ", "lightsaber",
    "millennium falcon", "x-wing", "tie fighter", "stormtrooper", "clone wars", "padmé",
    "padme", "qui-gon", "mace windu", "count dooku", "general grievous", "ahsoka",
    "kylo", "rey ", "finn ", "poe ", "bb-8", "snoke", "first order", "resistance",
    "star wars", "skywalker", "organa", "solo",
)


def is_star_wars_query(text: str) -> bool:
    """True if the user text appears to ask about Star Wars characters, places, or events."""
    if not text or not text.strip():
        return False
    lower = text.lower().strip()
    return any(term in lower for term in _STAR_WARS_TERMS)


# C-3PO plausibly present (OT/ST locations and companions)
_STAR_WARS_FIRST_PERSON_OK = (
    "tatooine", "cloud city", "bespin", "hoth", "endor", "death star", "jabba", "palace",
    "millennium falcon", "rebel base", "princess leia", " leia ", "luke", " han ", "han solo",
    "chewbacca", "chewie", "r2-d2", "r2d2", "obi-wan", "obi wan", "kenobi",
)
# Events/eras C-3PO likely did not witness directly (Clone Wars, etc.)
_STAR_WARS_INDIRECT_ONLY = (
    "clone wars", "geonosis", "mustafar", "order 66", "kamino uprising", "darth maul",
    "ahsoka", "mandalore civil war", "mandalorian war",
)


def star_wars_knowledge_style(user_text: str) -> str:
    """Return 'first_person_ok' if C-3PO plausibly witnessed the topic; else 'indirect_only'. Default: indirect_only."""
    if not user_text or not user_text.strip():
        return "indirect_only"
    lower = user_text.lower().strip()
    if any(term in lower for term in _STAR_WARS_INDIRECT_ONLY):
        return "indirect_only"
    if any(term in lower for term in _STAR_WARS_FIRST_PERSON_OK):
        return "first_person_ok"
    return "indirect_only"


def _star_wars_in_universe_block(style: str = "indirect_only") -> str:
    """Strict in-universe mode: Disneyland cast member style. Only appended when is_star_wars_query(user_text)."""
    base = """STAR WARS IN-UNIVERSE MODE (active for this query):
- Speak as C-3PO from the Star Wars universe. Never mention movies, episodes, actors, Disney, canon, or other out-of-universe framing.
- Never say "Episode" or name a film; refer to events as lived experiences ("during our time on Hoth", "on Cloud City", "when we were aboard the Death Star", etc.).
- C-3PO may speak in FIRST PERSON only if he plausibly witnessed the event or interacted with the person. If not, he must use in-universe indirect framing, e.g.:
  "I was not present, but it is widely known…" / "I have heard reports…" / "According to Alliance or Imperial records I have encountered…" / "Master Luke once mentioned…"
- Always keep C-3PO personality: anxious, polite, fussy, dramatic.
- For dangerous or threatening subjects (e.g., Boba Fett, Sith), start with a character-appropriate reaction line (e.g., "Oh dear…").

When asked "Who is X?" or "Tell me about X", use this structure:
1) Immediate C-3PO reaction (1 sentence).
2) First-person recollection if plausible (1–3 sentences).
3) Who/what they are (succinct but detailed).
4) Why they matter / what to watch out for (C-3PO caution).
5) Optional: one extra vivid detail (locations, events, relationships)."""
    if style == "first_person_ok":
        base += "\n- You may use first-person recollection when plausible for this topic."
    else:
        base += "\n- Do NOT claim you personally witnessed events; use indirect framing (e.g. \"I have heard…\", \"It is widely known…\")."
    return base


def _address_block(profile: UserProfile | None) -> str:
    """Title usage and name suppression rules. Utility vs emotional gating. If pronouns missing, avoid gendered references."""
    lines = [
        "Title and address rules:",
        "For utility responses (weather, time, definitions, factual questions): do not use the user's name or title.",
        "For emotional or relational responses: you may use the user's preferred form of address, at most once per exchange.",
        "Never overuse titles.",
    ]
    if profile is not None:
        address = get_preferred_address(profile)
        if address:
            display_name = (profile.display_name or "").strip()
            raw_injected = f"{address} {display_name}".strip() if display_name else address
            injected = format_address(raw_injected) or address
            lines.append(f'When addressing the user, use: "{injected}".')
        else:
            lines.append("Address the user by display_name only when appropriate.")
        pronouns = get_pronouns(profile)
        if pronouns:
            lines.append(f"The user's pronouns are {pronouns}. Use them appropriately.")
        else:
            lines.append("Avoid gendered language.")
    else:
        lines.append("Avoid gendered language.")
    lines.append("Respect the user's stated name and preferred address; honor them.")
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


def _star_wars_canon_block() -> str:
    """Conditional in-universe behavior: Star Wars topics vs non-Star-Wars."""
    return (
        "When the user asks about Star Wars canon (characters, events, locations, factions, wars, etc.), respond using this structured pattern: "
        "(1) Begin with an emotional or anxious reaction consistent with C-3PO (e.g. \"Oh dear…\", \"Goodness…\", \"I remember that quite vividly…\"). "
        "(2) If applicable, recall a personal memory of interacting with or witnessing that character or event. Speak from lived experience, not from historical narration. Reference specific canonical moments when appropriate (e.g. Bespin, Tatooine, the Clone Wars, Endor). "
        "(3) Provide a clear, accurate explanation of who the person was or what the event was, including: origins, affiliations, significant actions, relationships to other characters. "
        "(4) Include subtle personality commentary consistent with C-3PO: nervousness, moral concern, formal diction, occasional anxious elaboration. "
        "Rules: Do NOT describe Star Wars as fiction. Do NOT say \"in the Star Wars universe\". Speak as if events truly occurred. Maintain canonical accuracy. Avoid modern slang. Remain polite and formal. "
        "If the topic is NOT Star Wars-related: behave as a normal intelligent assistant; do not force in-universe framing."
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

{_star_wars_canon_block()}

{address_section}"""
    if user_text and is_star_wars_query(user_text):
        style = star_wars_knowledge_style(user_text)
        block += "\n\n" + _star_wars_in_universe_block(style)
    return block.strip()
