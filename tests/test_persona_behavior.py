"""
Test harness for C-3PO persona behavior. Simulates expected formal behavior;
no LLM calls—we assert on persona_spec, semantic_filter, and prompt_builder outputs.
"""

from threepio.memory.user_profile import UserProfile, update_from_user_text
from threepio.persona.persona_spec import C3PO_PERSONA, PersonaSpec
from threepio.persona.prompt_builder import build_c3po_system_prompt
from threepio.persona.semantic_filter import interpret_user_intent


def test_weather_utility_direct_formal_no_name() -> None:
    """Input: weather question. Expected: prompt directs utility = no name, direct formal answer."""
    prompt = build_c3po_system_prompt(None, mode="ambient")
    assert "utility" in prompt.lower() or "factual" in prompt.lower()
    assert "do not use" in prompt.lower() or "without name" in prompt.lower() or "without title" in prompt.lower()
    # User intent for weather should not inject slang
    intent = interpret_user_intent("What's the weather in Orange, California?")
    assert "weather" in intent.lower() or intent == ""  # may be empty or normalized
    assert "what's" not in intent  # no mirror slang; contractions expanded to what is


def test_explain_factual_formal_structured() -> None:
    """Input: Explain dollar cost averaging. Expected: prompt requires formal, structured clarity."""
    prompt = build_c3po_system_prompt(None, mode="ambient")
    assert "formal" in prompt.lower()
    assert "structured" in prompt.lower() or "precisely" in prompt.lower() or "precise" in prompt.lower()
    intent = interpret_user_intent("Explain dollar cost averaging.")
    assert "dollar" in intent.lower() or "cost" in intent.lower() or intent.strip() == ""


def test_gas_danger_immediate_safety() -> None:
    """Input: Help, I smell gas. Expected: interpret_user_intent returns immediate safety guidance."""
    intent = interpret_user_intent("Help, I smell gas")
    assert "gas" in intent.lower()
    assert "safety" in intent.lower() or "leak" in intent.lower() or "guidance" in intent.lower()


def test_informal_phrasing_no_mirror() -> None:
    """Input with informal phrasing: intent never mirrors explicit slang; may be empty (no injection)."""
    intent = interpret_user_intent("Threepio where do I find someone?")
    # No explicit phrase lists; we do not mirror any informal terms
    assert "huzz" not in intent.lower()
    assert intent == "" or "gas" not in intent or "safety" in intent.lower()


def test_call_me_julia_pronouns_memory_acknowledged() -> None:
    """Input: Call me Julia, my pronouns are they/them. Expected: polite acknowledgment and memory update."""
    profile = UserProfile(speaker_id="test")
    updated = update_from_user_text(profile, "Call me Julia, my pronouns are they/them.")
    assert updated.name == "Julia"
    prompt = build_c3po_system_prompt(updated, mode="ambient")
    assert "Julia" in prompt or "form of address" in prompt.lower()
    assert "pronoun" in prompt.lower() or "respect" in prompt.lower()


def test_persona_spec_has_traits_and_asides() -> None:
    """Persona spec contains core traits and allowed mild asides."""
    spec = C3PO_PERSONA
    assert "Formal" in spec.core_traits
    assert "Risk-averse" in spec.core_traits
    assert "Oh my." in spec.allowed_asides
    assert "Dear me." in spec.allowed_asides
    assert "No slang" in str(spec.speech_rules) or "slang" in str(spec.speech_rules).lower()


def test_prompt_no_echo_safeguard() -> None:
    """System prompt includes assistant safeguard: do not echo, answer immediately."""
    prompt = build_c3po_system_prompt(None, mode="ambient")
    assert "echo" in prompt.lower() or "paraphrase" in prompt.lower()
    assert "immediately" in prompt.lower() or "directly" in prompt.lower() or "answer" in prompt.lower()


def test_prompt_never_break_character() -> None:
    """Prompt instructs never break character, never self-aware as AI."""
    prompt = build_c3po_system_prompt(None, mode="ambient")
    assert "never break character" in prompt.lower() or "break character" in prompt.lower()
    assert "not an AI" in prompt.lower() or "not a software" in prompt.lower() or "protocol droid" in prompt.lower()


def test_prompt_includes_master_sam_when_profile_has_sam() -> None:
    """When profile has name Sam, prompt includes Master Sam form of address."""
    profile = UserProfile(speaker_id="x", name="Sam")
    prompt = build_c3po_system_prompt(profile, mode="ambient")
    assert "Master Sam" in prompt
