"""Stocks tool (mock unless REAL_TOOLS=1)."""

import os
from hashlib import sha256

from threepio.tools.types import ToolResult


def _mock_price(symbol: str) -> float:
    """Deterministic mock price from symbol hash."""
    h = sha256(symbol.upper().encode()).hexdigest()
    base = int(h[:8], 16) % 1000
    frac = int(h[8:12], 16) % 100
    return base + frac / 100


def get_stock_price(symbol: str) -> ToolResult:
    """Return stock price. Mock unless REAL_TOOLS=1."""
    symbol = symbol.strip().upper() or "AAPL"
    if os.environ.get("REAL_TOOLS") == "1":
        try:
            import urllib.request
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            req = urllib.request.Request(url, headers={"User-Agent": "THREEPIO/1.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                import json
                d = json.loads(r.read())
            meta = d.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price = meta.get("regularMarketPrice")
            if price is not None:
                return ToolResult(
                    tool_name="stocks",
                    ok=True,
                    data={"symbol": symbol, "price": price, "source": "yahoo"},
                )
        except Exception as e:
            return ToolResult(tool_name="stocks", ok=False, data={"source": "mock"}, error=str(e))
    price = _mock_price(symbol)
    return ToolResult(
        tool_name="stocks",
        ok=True,
        data={"symbol": symbol, "price": round(price, 2), "source": "mock"},
    )
