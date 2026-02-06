"""Eyes controller: parses settings and drives eye glow."""

from threepio.eyes.driver import EyeDriver, create_eye_driver


def _parse_amber_rgb(s: str) -> tuple[int, int, int]:
    """Parse 'r,g,b' string to tuple. Clamp 0-255."""
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 3:
        return (255, 150, 40)  # default amber
    try:
        r = max(0, min(255, int(parts[0])))
        g = max(0, min(255, int(parts[1])))
        b = max(0, min(255, int(parts[2])))
        return (r, g, b)
    except ValueError:
        return (255, 150, 40)


class EyesController:
    """Controls C-3PO eye glow from settings."""

    def __init__(self) -> None:
        from threepio.config import get_settings
        s = get_settings()
        self._driver: EyeDriver = create_eye_driver()
        self._rgb = _parse_amber_rgb(s.EYES_AMBER_RGB)
        self._brightness = max(0.0, min(1.0, s.EYES_BRIGHTNESS))

    def start(self) -> None:
        """Turn eyes ON (static amber glow)."""
        self._driver.on(self._rgb, self._brightness)

    def shutdown(self) -> None:
        """Turn eyes OFF."""
        self._driver.off()
