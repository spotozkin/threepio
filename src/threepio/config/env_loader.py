"""Environment loading with pytest and manual opt-out guards."""

import os
from pathlib import Path

from dotenv import load_dotenv


def _should_load_dotenv() -> bool:
    """False when running under pytest or when manually disabled."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    if os.getenv("THREEPIO_DISABLE_DOTENV", "").lower() in {"1", "true", "yes"}:
        return False
    return True


def _maybe_load_dotenv() -> None:
    """Load .env into os.environ unless guarded (pytest or THREEPIO_DISABLE_DOTENV)."""
    if not _should_load_dotenv():
        return
    dotenv_path = Path(".env")
    if dotenv_path.exists():
        load_dotenv(dotenv_path=dotenv_path)
