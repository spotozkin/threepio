"""Tests for ThreepioPersona C-3PO voice."""

import pytest

from threepio.brain.persona import ThreepioPersona

POLITE_MARKERS = (
    "Certainly",
    "Oh my",
    "I beg your pardon",
    "Good heavens",
    "As you wish",
    "I am pleased to report",
    "If I may",
    "Sir",
    "Madam",
    "apologize",
    "do take",
)


def _has_polite_marker(text: str) -> bool:
    return any(m in text for m in POLITE_MARKERS)


def test_format_tool_response_time_includes_fact_and_polite() -> None:
    """Time response includes time fact and a polite marker."""
    p = ThreepioPersona()
    result = p.format_tool_response("time", {"iso": "2025-02-05T14:30:00"}, "what time")
    assert "14:30" in result or "2:30" in result
    assert _has_polite_marker(result)


def test_format_tool_response_stocks_includes_fact_and_polite() -> None:
    """Stocks response includes symbol/price and a polite marker."""
    p = ThreepioPersona()
    result = p.format_tool_response("stocks", {"symbol": "NVDA", "price": 426.53, "source": "mock"}, "stock price")
    assert "NVDA" in result
    assert "426" in result
    assert _has_polite_marker(result)


def test_format_tool_response_weather_includes_fact_and_polite() -> None:
    """Weather response includes location/temp/condition and a polite marker."""
    p = ThreepioPersona()
    result = p.format_tool_response(
        "weather",
        {"location": "Anaheim", "temp_f": 72.5, "condition": "sunny"},
        "weather in Anaheim",
    )
    assert "Anaheim" in result
    assert "72" in result
    assert "sunny" in result
    assert _has_polite_marker(result)


def test_format_generic_response_has_polite_marker() -> None:
    """Generic response includes polite marker."""
    p = ThreepioPersona()
    result = p.format_generic_response("tell me about quantum physics")
    assert _has_polite_marker(result)
    assert "C-3PO" in result


def test_format_error_has_polite_marker() -> None:
    """Error response includes polite marker."""
    p = ThreepioPersona()
    result = p.format_error("Connection failed")
    assert _has_polite_marker(result)
    assert "Connection failed" in result or "apologize" in result.lower()
