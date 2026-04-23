"""Audio device listing and resolution. Standalone, dependency-light."""

from __future__ import annotations


def _val(d: object, key: str, default: object = None) -> object:
    """Get value from device (dict-like or attribute)."""
    try:
        return d.get(key, default)
    except (AttributeError, TypeError):
        return getattr(d, key, default)


def list_input_devices() -> list[tuple[int, str, int]]:
    """Return list of (index, name, max_input_channels) for devices with max_input_channels > 0."""
    import sounddevice as sd

    devs = sd.query_devices()
    result: list[tuple[int, str, int]] = []
    for i, d in enumerate(devs):
        mi = _val(d, "max_input_channels", 0)
        try:
            mi = int(mi or 0)
        except (TypeError, ValueError):
            mi = 0
        if mi <= 0:
            continue
        name = _val(d, "name", "") or ""
        name = (str(name) or "").strip() or f"device {i}"
        result.append((i, name, mi))
    return result


def resolve_input_device(selector: str | None) -> tuple[int, str]:
    """
    Resolve selector to (index, name).
    - None/empty: first input device; else raise RuntimeError.
    - Digit string: index; validate; else raise with available list.
    - Else: substring match (case-insensitive); first match; else raise with available list.
    """
    devs = list_input_devices()
    if not devs:
        raise RuntimeError("No audio input devices found")

    raw = (selector or "").strip()

    if not raw:
        idx, name, _ = devs[0]
        return (idx, name)

    if raw.isdigit():
        idx = int(raw)
        for i, name, _ in devs:
            if i == idx:
                return (idx, name)
        avail = format_input_devices(devs)
        raise RuntimeError(
            "Invalid audio input device index %s; no input-capable device at that index. Available:\n%s"
            % (idx, avail)
        )

    sub = raw.lower()
    for i, name, _ in devs:
        if sub in name.lower():
            return (i, name)
    avail = format_input_devices(devs)
    raise RuntimeError("No audio input device matching %r. Available:\n%s" % (raw, avail))


def format_input_devices(devs: list[tuple[int, str, int]]) -> str:
    """Return newline-joined lines: [index] Name (inputs: X)."""
    return "\n".join("[%d] %s (inputs: %d)" % (i, name, mi) for i, name, mi in devs)
