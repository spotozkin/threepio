"""
Load persona pack from JSON or generate from PersonaSpec. Module-level cache to avoid repeated disk reads.
"""

from __future__ import annotations

import json
from pathlib import Path

from threepio.persona.pack_schema import PersonaPack, validate_pack
from threepio.persona.persona_spec import C3PO_PERSONA, generate_persona_pack

_DEFAULT_PATH = Path(__file__).resolve().parent / "c3po_pack.v1.json"
_CACHE: dict[str, PersonaPack] = {}  # key: "" for generated, path string for file


def load_persona_pack(pack_path: str | None = None) -> PersonaPack:
    """
    Return persona pack: from JSON file if pack_path is provided and file exists; otherwise from PersonaSpec.
    Uses cache per source (generated vs path). Never raises FileNotFoundError: falls back to generated pack if file missing.
    """
    global _CACHE
    if pack_path:
        resolved = Path(pack_path).resolve()
        if resolved.is_file():
            key = str(resolved)
            if key not in _CACHE:
                with open(resolved, encoding="utf-8") as f:
                    data = json.load(f)
                _CACHE[key] = validate_pack(data)
            return _CACHE[key]
    # Default or missing file: generate from PersonaSpec
    if "" not in _CACHE:
        _CACHE[""] = generate_persona_pack(C3PO_PERSONA)
    return _CACHE[""]


def clear_persona_pack_cache() -> None:
    """Clear the module-level pack cache (for tests)."""
    global _CACHE
    _CACHE.clear()
