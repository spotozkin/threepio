"""Rich logging configuration."""

import logging
import sys
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler


def setup_logging(level: str = "INFO", force: bool = False) -> None:
    """Configure rich logging for the application."""
    root = logging.getLogger()
    if root.handlers and not force:
        return

    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    handler = RichHandler(
        console=Console(stderr=True),
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    root.addHandler(handler)

    # Quiet noisy libs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
