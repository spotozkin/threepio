"""Runtime logging: rich if available, else minimal."""

import logging
import sys


def setup_runtime_logging(level: str = "INFO") -> None:
    """Configure logging. Uses rich if installed."""
    try:
        from threepio.core.logging import setup_logging
        setup_logging(level=level)
    except ImportError:
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stderr,
        )
