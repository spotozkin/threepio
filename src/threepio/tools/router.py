"""Tool router: heuristics and execution."""

import re
import logging
from typing import Any

from threepio.tools.types import ToolResult
from threepio.tools.time_tool import get_local_time
from threepio.tools.stocks_tool import get_stock_price
from threepio.tools.weather_tool import get_weather

logger = logging.getLogger(__name__)

CallSpec = dict[str, Any]
TOOL_REGISTRY = {
    "time": get_local_time,
    "stocks": get_stock_price,
    "weather": get_weather,
}


def _extract_ticker(text: str) -> str | None:
    """Find first ticker-like token (2-5 uppercase letters)."""
    m = re.search(r"\b([A-Z]{2,5})\b", text)
    return m.group(1) if m else None


def _extract_location(text: str) -> str:
    """Naive: text after 'in '."""
    m = re.search(r"\bin\s+([^.?!]+)", text, re.I)
    return m.group(1).strip() if m else "unknown"


class ToolRouter:
    """Routes user text to tool calls and executes them."""

    def route(self, user_text: str) -> list[CallSpec]:
        """Return list of call specs from user text."""
        text = user_text.lower()
        specs: list[CallSpec] = []

        if "time" in text:
            specs.append({"tool": "time", "args": {}})
        if "weather" in text or "temperature" in text:
            specs.append({"tool": "weather", "args": {"location": _extract_location(user_text)}})
        if any(x in text for x in ["stock", "price", "$"]):
            ticker = _extract_ticker(user_text) or "AAPL"
            specs.append({"tool": "stocks", "args": {"symbol": ticker}})

        return specs

    def execute(self, specs: list[CallSpec]) -> list[ToolResult]:
        """Execute tool specs and return results."""
        results: list[ToolResult] = []
        for s in specs:
            name = s.get("tool", "")
            args = s.get("args", {})
            fn = TOOL_REGISTRY.get(name)
            if fn:
                try:
                    if name == "time":
                        r = get_local_time()
                    elif name == "stocks":
                        r = get_stock_price(args.get("symbol", "AAPL"))
                    elif name == "weather":
                        r = get_weather(args.get("location", "unknown"))
                    else:
                        r = ToolResult(tool_name=name, ok=False, data={}, error="unknown tool")
                    results.append(r)
                    logger.info("Tool %s: ok=%s", name, r.ok)
                except Exception as e:
                    results.append(ToolResult(tool_name=name, ok=False, data={}, error=str(e)))
                    logger.exception("Tool %s failed", name)
        return results
