"""LED driver for eyes (mock prints state changes)."""

import logging

logger = logging.getLogger(__name__)


class MockLEDDriver:
    """Mock LED driver: prints state changes to log."""

    def __init__(self) -> None:
        self._on = False

    def on(self) -> None:
        """Turn eyes ON."""
        if not self._on:
            self._on = True
            logger.info("[LED] Eyes ON")

    def off(self) -> None:
        """Turn eyes OFF."""
        if self._on:
            self._on = False
            logger.info("[LED] Eyes OFF")
