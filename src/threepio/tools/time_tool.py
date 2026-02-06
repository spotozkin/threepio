"""Time tool."""

import time
from datetime import datetime

from threepio.tools.types import ToolResult


def get_local_time() -> ToolResult:
    """Return local time in ISO format with timezone."""
    try:
        now = datetime.now()
        tz = time.tzname
        tz_name = tz[0] if tz else "local"
        try:
            local_tz = datetime.now().astimezone().tzinfo
            if local_tz:
                tz_name = str(local_tz)
        except Exception:
            pass
        return ToolResult(
            tool_name="time",
            ok=True,
            data={
                "iso": now.isoformat(),
                "tz": tz_name,
            },
        )
    except Exception as e:
        return ToolResult(tool_name="time", ok=False, data={}, error=str(e))
