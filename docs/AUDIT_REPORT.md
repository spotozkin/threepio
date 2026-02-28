# THREEPIO Repo Audit Report

## 1. Dependency Map

### Persona / prompt chain
```
prompt_builder.py
  ← loader.load_persona_pack, intent_router.route_intent, flavor_governor.decide_flavor, prompt_blocks.render_persona_block
loader.py
  ← pack_schema.PersonaPack, validate_pack; persona_spec.C3PO_PERSONA, generate_persona_pack
persona_spec.py
  ← pack_schema.PersonaPack
pack_schema.py
  (no internal threepio imports)
prompt_blocks.py
  ← pack_schema.PersonaPack
intent_router.py
  (no runtime loader import; TYPE_CHECKING pack_schema.PersonaPack)
flavor_governor.py
  (no persona imports)
semantic_filter.py
  (only re; no persona_spec after slang removal)
slang.py
  ← TYPE_CHECKING pack_schema.PersonaPack
```
**Callers of persona/prompt:**
- `modes/ambient.py` → build_c3po_system_prompt, route_intent (via prompt_builder), interpret_user_intent (semantic_filter)
- Tests: prompt_builder, persona_contract, persona_behavior, slang_*, etc.

### Audio / VAD / playback
```
vad.py
  (logging, os, threading, time, queue, deque; no threepio imports)
modes/ambient.py
  ← audio.mic_stream, audio.vad, speech.playback
audio/player.py
  ← speech.playback (play_audio_file, resolve_playback_mode)
speech/playback.py
  (no threepio persona/audio imports)
```
**Callers:** ambient, tests (test_bargein_*, test_playback_platform)

### Brain / LLM / tools
```
brain/respond.py
  ← brain.persona.ThreepioPersona, memory.memory, tools.router
brain/persona.py
  (no threepio imports)
brain/llm/mock_llm.py
  ← brain.llm.base, character.persona.PERSONA_RULES, core.types
```
**Callers:** app.py (Responder), streaming_chat (Responder, ToolRouter)

### Core
```
core/__init__.py
  → only core.types.DialogueTurn
core/
  types.py, logging.py, healthcheck.py  (no events.py, state.py, state_machine.py, logging_subscriber.py)
```

### Chat
```
chat/streaming_chat.py
  ← brain.respond, chat.cancel, chat.conversation, config, core.events, core.logging_subscriber, core.state, core.state_machine, speech.tts, tools.router
```
**Problem:** `core.events`, `core.state`, `core.state_machine`, `core.logging_subscriber` do **not** exist under `core/`.

### Module → imported by (summary)
| Module | Imported by |
|--------|-------------|
| persona_spec | loader |
| pack_schema | loader, persona_spec, prompt_blocks, intent_router (TYPE_CHECKING), slang (TYPE_CHECKING) |
| loader | prompt_builder, tests |
| prompt_blocks | prompt_builder |
| prompt_builder | modes/ambient (dynamic), tests |
| intent_router | prompt_builder |
| flavor_governor | prompt_builder, modes/ambient (flavor_intent loaded but never called) |
| semantic_filter | modes/ambient (dynamic) |
| slang | tests only (test_slang_*) |
| character.persona | brain/llm/mock_llm |
| speech.echo_guard, speech.text_shaping | modes/ambient |
| speech.playback | modes/ambient, audio/player |

---

## 2. Issues by Severity

### CRITICAL

- **Missing modules: `streaming_chat` will fail on import**  
  - **File:** `src/threepio/chat/streaming_chat.py`  
  - **Symbols:** `from threepio.core.events import EventBus`; `from threepio.core.logging_subscriber import create_logging_subscriber`; `from threepio.core.state import DroidEvent`; `from threepio.core.state_machine import StateMachine`  
  - **What’s wrong:** `core/` only contains `__init__.py`, `types.py`, `logging.py`, `healthcheck.py`. There are no `events.py`, `state.py`, `state_machine.py`, or `logging_subscriber.py`. Running `python -m threepio.chat.streaming_chat` (or any import of `streaming_chat`) raises `ModuleNotFoundError`.  
  - **Fix:** Either (1) add the missing modules under `core/` (EventBus, DroidEvent, StateMachine, create_logging_subscriber) with minimal implementations that match current usage in `streaming_chat.py`, or (2) remove or replace the dependency (e.g. inline or move to `chat/`) so `streaming_chat` does not import from `core.events` / `core.state` / `core.state_machine` / `core.logging_subscriber`.

---

### HIGH

- **Outdated docstring in `intent_router`**  
  - **File:** `src/threepio/persona/intent_router.py`  
  - **Symbol:** `route_intent` docstring  
  - **What’s wrong:** Docstring says “Uses persona pack slang_map for social_slang detection” and “Pass pack if already loaded to avoid reloading.” Implementation no longer uses `pack` or `slang_map`; social_slang is keyword-based only.  
  - **Fix:** Update docstring to: “Classify user text into intent. social_slang is detected via normal keywords only (e.g. dating, relationship, partner). Order: urgent > utility > explanation > social_slang > general. pack/pack_path are accepted for API compatibility but not used.”

- **Unused parameter and dead load in `route_intent`**  
  - **File:** `src/threepio/persona/intent_router.py`  
  - **Symbol:** `route_intent(..., pack_path=..., pack=...)`  
  - **What’s wrong:** `pack_path` and `pack` are never used. Callers (e.g. prompt_builder) still pass `pack=pack`. No functional bug but misleading API.  
  - **Fix:** Either keep parameters for compatibility and document “reserved for future use” or remove and update `prompt_builder.build_c3po_system_prompt` to call `route_intent(user_text)` only.

- **Stale exception in `prompt_builder`**  
  - **File:** `src/threepio/persona/prompt_builder.py`  
  - **Symbol:** `build_c3po_system_prompt`, `except (FileNotFoundError, ValueError)`  
  - **What’s wrong:** `load_persona_pack()` no longer raises `FileNotFoundError` (it falls back to generated pack). Only `ValueError` can be raised (e.g. from `validate_pack` when loading from file). Catching `FileNotFoundError` is redundant.  
  - **Fix:** Use `except ValueError:` (or catch a broader `Exception` only if you want to guard against any load failure). Optional: add a short comment that loader now returns generated pack by default.

- **Unused variable in ambient: `flavor_intent`**  
  - **File:** `src/threepio/modes/ambient.py`  
  - **Symbol:** `flavor_intent = _load_flavor_governor_fn()`  
  - **What’s wrong:** `flavor_intent` is loaded but never called. `decide_flavor` is used with `intent` from `route_intent` (in prompt_builder), not with `flavor_intent`. Dead code.  
  - **Fix:** Remove the load and use of `flavor_intent` in `run_ambient` (and simplify `_load_flavor_governor_fn` to only load what’s needed, or remove it if nothing else needs it), or start using `flavor_intent` somewhere and document how it relates to `route_intent`.

---

### MEDIUM

- **Two persona systems; naming overlap**  
  - **Files:** `src/threepio/brain/persona.py` (ThreepioPersona) vs `src/threepio/persona/` (PersonaSpec, PersonaPack, prompt_builder)  
  - **What’s wrong:** “Persona” is used for (1) tool-formatting / generic response (ThreepioPersona) and (2) LLM system prompt / intent/flavor (PersonaSpec, PersonaPack, prompt_builder). Both are valid but the split can confuse readers and look inconsistent on a portfolio.  
  - **Fix:** In docs or README, clarify: “Persona (brain): response formatting for tools. Persona (persona/): system prompt and intent/flavor for LLM.” Optionally rename `brain/persona.py` to e.g. `brain/response_formatter.py` and class to `ThreepioResponseFormatter` for clarity.

- **Optional module `reality_threepio` referenced but missing**  
  - **File:** `src/threepio/modes/ambient.py`  
  - **Symbol:** `_load_slang_gloss_fn()` → `from threepio.persona.reality_threepio import slang_to_formal_gloss`  
  - **What’s wrong:** Module `persona/reality_threepio.py` does not exist. Fallback `lambda text: ""` is used. No crash but the name suggests an optional “reality” layer that isn’t in the repo.  
  - **Fix:** Either add a stub `persona/reality_threepio.py` with `def slang_to_formal_gloss(text: str) -> str: return ""` and a short docstring, or rename the loader to something like `_load_optional_gloss_fn` and document that the optional module is not shipped (portfolio-only).

- **`interpret_slang` always returns empty labels when `slang_map` is empty**  
  - **File:** `src/threepio/persona/slang.py`  
  - **Symbol:** `interpret_slang(text, pack)`  
  - **What’s wrong:** With empty `pack.slang_map` (current design), the function always returns `(text, [])`. Any caller that expects labels will get none. Behavior is correct but the module’s purpose is now minimal.  
  - **Fix:** No code change required if design is “no explicit slang in repo.” Optionally add a one-line docstring: “When pack.slang_map is empty, returns (text, []); labels are only present when a pack with slang_map entries is provided.”

- **Prompt instruction vs behavior after slang removal**  
  - **Files:** `persona/prompt_blocks.py`, `persona/prompt_builder.py`, `persona/semantic_filter.py`  
  - **What’s wrong:** Prompt still says “Interpret modern slang silently into formal meaning” and “Do not repeat or mirror slang phrasing.” Semantic_filter only returns a non-empty string for gas-leak safety; it no longer injects phrase interpretations. So “interpret informal phrasing” is entirely delegated to the model via the prompt.  
  - **Fix:** No bug. For portfolio, you can add a short comment in `semantic_filter` or README: “Informal phrasing is handled by the model per prompt instructions; this module only does normalization and safety (e.g. gas leak) detection.”

---

### LOW

- **`pack_schema.validate_pack`: empty `slang_map` is valid**  
  - **File:** `src/threepio/persona/pack_schema.py`  
  - **What’s wrong:** Validation requires each slang_map value to have `"meaning"` (and optional `"label"` as str). Empty `slang_map` is valid (loop runs zero times). No issue.  
  - **Fix:** None.

- **VAD barge-in: `set_speaking_start_ts` not set**  
  - **File:** `src/threepio/audio/vad.py`  
  - **Symbol:** `VADMonitor`, `_speaking_start_ts`, `get_speech_suppress_ms()`  
  - **What’s wrong:** In barge_in mode, suppression uses `_speaking_start_ts`. If the caller never calls `set_speaking_start_ts()`, it stays `None` and `elapsed_ms` is set to `suppress_ms + 1`, so suppression is effectively skipped. Tests set it explicitly.  
  - **Fix:** Document in `VADMonitor` docstring or in `set_speaking_start_ts`: “In barge_in mode, call set_speaking_start_ts when TTS starts so the suppression window applies; otherwise barge-in may fire immediately.”

- **Duplicate “no echo” / “answer immediately” style rules**  
  - **Files:** `persona/prompt_blocks.py` (style_rules from pack), `persona/prompt_builder.py` (hardcoded “Answering rules: Do not echo…”)  
  - **What’s wrong:** The same idea appears in the generated style_rules (persona_spec → pack) and again in the fixed “Answering rules” block. Slightly redundant but not contradictory.  
  - **Fix:** Optional: remove the duplicate from generated style_rules and keep a single “Do not echo; answer immediately” in the prompt_builder block.

---

## 3. Recommended Patches (concise)

### 3.1 Fix streaming_chat import (CRITICAL)

Either create the missing modules or stop importing them.

**Option A – Stub modules under `core/` (minimal):**

```python
# core/events.py
class EventBus:
    def __init__(self): self._subs = []
    def subscribe(self, fn): self._subs.append(fn)
    def emit(self, event): [f(event) for f in self._subs]

# core/state.py
from dataclasses import dataclass
from typing import Any
@dataclass
class DroidEvent:
    type: str
    payload: dict[str, Any]

# core/state_machine.py
class StateMachine:
    def __init__(self, bus): self._bus = bus

# core/logging_subscriber.py
def create_logging_subscriber():
    return lambda event: None  # or logging.info("event: %s", event)
```

**Option B – Inline in `streaming_chat`:** Move EventBus, DroidEvent, StateMachine, and a small logging subscriber into `chat/streaming_chat.py` (or a new `chat/events.py`) and remove the `core.*` imports.

### 3.2 intent_router docstring and API (HIGH)

```python
# intent_router.py
def route_intent(
    user_text: str,
    pack_path: str | None = None,
    pack: PersonaPack | None = None,
) -> IntentType:
    """
    Classify user text into intent. social_slang is detected via normal keywords only
    (e.g. dating, relationship, partner). Order: urgent > utility > explanation > social_slang > general.
    pack and pack_path are accepted for API compatibility but not used.
    """
```

### 3.3 prompt_builder exception (HIGH)

```python
# prompt_builder.py
try:
    pack = load_persona_pack()
    persona_section = render_persona_block(pack)
except ValueError:
    persona_section = _persona_block_fallback()
    pack = None
```

### 3.4 ambient: remove unused flavor_intent (HIGH)

In `run_ambient`, remove the line that assigns `flavor_intent = _load_flavor_governor_fn()` if it is never used. If `_load_flavor_governor_fn` is only for that, remove the loader or repurpose it for loading `decide_flavor` if needed elsewhere.

---

## 4. Portfolio Readiness

- **Rename / clarify**
  - Consider renaming `brain/persona.py` → `brain/response_formatter.py` (and class) so “persona” is clearly the persona/ pack + prompt stack.
  - Add a one-sentence README note: “Persona (persona/): LLM system prompt and intent. Persona (brain): tool response formatting.”

- **Remove or implement dead/optional paths**
  - Fix or remove `streaming_chat`’s dependency on missing `core` modules so `python -m threepio.chat.streaming_chat` runs or is clearly marked as deprecated.
  - Either add a stub `persona/reality_threepio.py` or document that the optional gloss module is not included.

- **Docs**
  - In README or docs, state that “interpret informal phrasing” is achieved by prompt instructions and optional semantic_filter (normalization + gas-leak only); no explicit slang lists are in the repo.
  - Document VAD barge-in: when to call `set_speaking_start_ts` and what happens if it’s not set.

- **Consistency**
  - Align docstrings with current behavior (intent_router, prompt_builder).
  - Single place for “do not echo; answer immediately” if you want to avoid duplication.

- **Tests**
  - Add a test that imports `threepio.chat.streaming_chat` (or run its main) so the critical import path is regression-tested once the missing core modules are added or the imports are removed.

---

## 5. Ambient voice (laptop demo) – env and commands

Use these so ambient respects input device, min utterance, and C-3PO FX:

```bash
export THREEPIO_AUDIO_INPUT_DEVICE=1
export THREEPIO_MIN_UTTERANCE_SEC=0.7
export ENABLE_C3PO_FX=true
THREEPIO_DEBUG=1 AUDIO_OUTPUT_MODE=afplay python -m threepio.modes.ambient
```

- **Input device:** `THREEPIO_AUDIO_INPUT_DEVICE` (not `INPUT_DEVICE`). Resolved via `threepio.audio.mic_stream.resolve_audio_input_device()`; startup log prints resolved index + name.
- **Min utterance:** `THREEPIO_MIN_UTTERANCE_SEC` (float, default 1.2); logged when `THREEPIO_DEBUG=1`.
- **C-3PO FX:** `ENABLE_C3PO_FX` (bool); `Settings` defines it; ambient uses `getattr(settings, "ENABLE_C3PO_FX", False)` so it never crashes if the attribute is missing.

## 6. Slang removal and “interpret informal phrasing”

- **persona_spec:** `CANONICAL_SLANG_MAP = {}`; `generate_persona_pack()` produces `slang_map={}`. No explicit slang in repo.
- **intent_router:** social_slang only via keywords (dating, relationship, courtship, partner, boyfriend, girlfriend). No pack.slang_map use.
- **semantic_filter:** Only normalization and gas-leak safety; returns "" otherwise. No phrase-to-meaning map.
- **Prompt:** Still instructs the model to “Interpret modern slang silently…” and “Do not repeat or mirror slang phrasing.” So “interpret informal phrasing” is preserved via the model, not via in-code slang lists. Safe and consistent for a portfolio.
