"""Weather tool (mock unless REAL_TOOLS=1)."""

import os
from hashlib import sha256

from threepio.tools.types import ToolResult


def _mock_weather(location: str) -> tuple[float, str]:
    """Deterministic mock temp and condition from location hash."""
    h = sha256(location.lower().encode()).hexdigest()
    temp = 50 + (int(h[:4], 16) % 60)
    conditions = ["sunny", "cloudy", "partly cloudy", "clear", "overcast"]
    cond = conditions[int(h[4:8], 16) % len(conditions)]
    return float(temp), cond


def get_weather(location: str) -> ToolResult:
    """Return weather for location. Mock unless REAL_TOOLS=1."""
    location = location.strip() or "unknown"
    if os.environ.get("REAL_TOOLS") == "1":
        try:
            import urllib.parse
            import urllib.request
            q = urllib.parse.quote(location)
            url = f"https://wttr.in/{q}?format=j1"
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                import json
                d = json.loads(r.read())
            curr = d.get("current_condition", [{}])[0]
            temp_c = float(curr.get("temp_C", 20))
            desc = curr.get("weatherDesc", [{}])[0].get("value", "unknown")
            return ToolResult(
                tool_name="weather",
                ok=True,
                data={"location": location, "temp_f": round(temp_c * 9 / 5 + 32, 1), "condition": desc, "source": "wttr"},
            )
        except Exception as e:
            temp, cond = _mock_weather(location)
            return ToolResult(
                tool_name="weather",
                ok=False,
                data={"location": location, "temp_f": temp, "condition": cond, "source": "mock", "error": str(e)},
                error=str(e),
            )
    temp, cond = _mock_weather(location)
    return ToolResult(
        tool_name="weather",
        ok=True,
        data={"location": location, "temp_f": temp, "condition": cond, "source": "mock"},
    )
