"""Neatlogs beyond the SDK: HTTP /v1/trace write-back (server-side nlw_ key) and MCP read-back (project key)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from . import config


def post_trace(trace: dict, timeout: float = 15.0) -> dict:
    """POST one nested trace to /v1/trace with the per-user write key. Never called from the browser."""
    body = {"project": config.NEATLOGS_PROJECT, **trace}
    r = httpx.post(f"{config.NEATLOGS_ENDPOINT}/v1/trace", json=body, timeout=timeout,
                   headers={"Authorization": f"Bearer {config.NEATLOGS_WRITE_KEY}"})
    r.raise_for_status()
    return r.json()


async def _mcp_call(calls: list[tuple[str, dict]]) -> list[Any]:
    import httpx2
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    headers = {"Authorization": f"Bearer {config.NEATLOGS_API_KEY}"}
    out: list[Any] = []
    async with httpx2.AsyncClient(headers=headers, timeout=httpx2.Timeout(30, read=60)) as http, \
            streamable_http_client(config.NEATLOGS_MCP_URL, http_client=http) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for name, args in calls:
                if name == "__list_tools__":
                    tools = await session.list_tools()
                    out.append([{"name": t.name, "schema": t.input_schema} for t in tools.tools])
                    continue
                res = await session.call_tool(name, args)
                out.append(_content(res))
    return out


def _content(res: Any) -> Any:
    if getattr(res, "structured_content", None):
        return res.structured_content
    texts = [c.text for c in res.content if getattr(c, "type", "") == "text"]
    joined = "\n".join(texts)
    try:
        return json.loads(joined)
    except (ValueError, TypeError):
        return joined


def mcp(calls: list[tuple[str, dict]], timeout: float = 30.0) -> list[Any]:
    """Run MCP tool calls in one session. Synchronous wrapper for scripts and threadpool routes."""
    return asyncio.run(asyncio.wait_for(_mcp_call(calls), timeout))
