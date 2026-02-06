"""Eye drivers: mock and NeoPixel."""

import logging
from typing import Protocol

from threepio.config import get_settings

logger = logging.getLogger(__name__)

SUPPORTED_PINS = ("D18", "D21", "D10")


def _pin_to_board(pin_str: str):
    """Map pin string (e.g. D18) to board pin. Raises ValueError if unknown."""
    if pin_str not in SUPPORTED_PINS:
        raise ValueError(
            f"Unsupported EYES_PIN '{pin_str}'. Supported: {', '.join(SUPPORTED_PINS)}"
        )
    import board
    return getattr(board, pin_str)


class EyeDriver(Protocol):
    """Protocol for eye drivers."""

    def on(self, rgb: tuple[int, int, int], brightness: float) -> None:
        """Turn eyes ON with given RGB and brightness."""
        ...

    def off(self) -> None:
        """Turn eyes OFF."""
        ...


class MockEyeDriver:
    """Mock driver: prints state changes."""

    def on(self, rgb: tuple[int, int, int], brightness: float) -> None:
        logger.info("[EYES] ON rgb=%s, brightness=%s", rgb, brightness)
        print(f"[EYES] ON rgb={rgb}, brightness={brightness}")

    def off(self) -> None:
        logger.info("[EYES] OFF")
        print("[EYES] OFF")


class NeoPixelEyeDriver:
    """Adafruit NeoPixel driver for C-3PO amber glow."""

    def __init__(self, pin, num_pixels: int) -> None:
        import neopixel
        self._pixels = neopixel.NeoPixel(
            pin,
            num_pixels,
            brightness=1.0,  # Set per on() call
            auto_write=False,
            pixel_order=neopixel.GRB,
        )
        self._num_pixels = num_pixels

    def on(self, rgb: tuple[int, int, int], brightness: float) -> None:
        self._pixels.brightness = max(0.0, min(1.0, brightness))
        self._pixels.fill(rgb)
        self._pixels.show()

    def off(self) -> None:
        self._pixels.fill((0, 0, 0))
        self._pixels.show()


def create_eye_driver() -> EyeDriver:
    """Create eye driver from settings. Falls back to mock on import/config errors."""
    settings = get_settings()
    if settings.PROVIDER_EYES == "mock":
        return MockEyeDriver()

    if settings.PROVIDER_EYES == "neopixel":
        try:
            pin = _pin_to_board(settings.EYES_PIN)
            n = settings.EYES_PIXEL_COUNT
            if settings.EYES_CHAIN_MODE == "dual":
                raise NotImplementedError("EYES_CHAIN_MODE=dual not yet implemented")
            return NeoPixelEyeDriver(pin, n)
        except (ImportError, NotImplementedError, ValueError) as e:
            logger.warning("NeoPixel eyes unavailable (%s), using MockEyeDriver", e)
            return MockEyeDriver()

    return MockEyeDriver()
