"""Small helpers around the neatlogs SDK."""
from __future__ import annotations

import neatlogs


def current_trace_id() -> str | None:
    """The 32-hex trace id of the active neatlogs span (the id the dashboard and MCP server use)."""
    carrier: dict = {}
    if not neatlogs.inject_trace_context(carrier):
        return None
    parts = carrier.get("traceparent", "").split("-")
    return parts[1] if len(parts) == 4 else None

