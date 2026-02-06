"""Tool result types."""

from dataclasses import dataclass


@dataclass
class ToolResult:
    """Result of a tool call."""

    tool_name: str
    ok: bool
    data: dict
    error: str | None = None
