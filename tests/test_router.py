"""Tests for tool router heuristics."""

import pytest

from threepio.tools.router import ToolRouter


def test_route_time() -> None:
    """Time-related text routes to time tool."""
    r = ToolRouter()
    specs = r.route("what time is it")
    assert len(specs) >= 1
    assert any(s["tool"] == "time" for s in specs)


def test_route_weather() -> None:
    """Weather-related text routes to weather tool."""
    r = ToolRouter()
    specs = r.route("weather in Anaheim")
    assert len(specs) >= 1
    assert any(s["tool"] == "weather" for s in specs)
    w = next(s for s in specs if s["tool"] == "weather")
    assert "Anaheim" in w["args"].get("location", "")


def test_route_stocks() -> None:
    """Stock-related text routes to stocks tool."""
    r = ToolRouter()
    specs = r.route("stock price of NVDA")
    assert len(specs) >= 1
    assert any(s["tool"] == "stocks" for s in specs)
    s = next(x for x in specs if x["tool"] == "stocks")
    assert s["args"].get("symbol") == "NVDA"


def test_execute_time() -> None:
    """Time tool executes and returns ok result."""
    r = ToolRouter()
    results = r.execute([{"tool": "time", "args": {}}])
    assert len(results) == 1
    assert results[0].tool_name == "time"
    assert results[0].ok
    assert "iso" in results[0].data


def test_execute_stocks_mock() -> None:
    """Stocks tool returns mock data."""
    r = ToolRouter()
    results = r.execute([{"tool": "stocks", "args": {"symbol": "NVDA"}}])
    assert len(results) == 1
    assert results[0].ok
    assert results[0].data.get("symbol") == "NVDA"
    assert "price" in results[0].data
