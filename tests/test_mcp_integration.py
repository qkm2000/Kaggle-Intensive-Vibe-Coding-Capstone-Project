"""End-to-end MCP integration test.

Spawns the real LedgerLens MCP server as a subprocess and drives it with the
official MCP client over stdio — proving the server speaks the protocol, not
just that its Python functions return dicts. Skipped if the ``mcp`` client
transport isn't importable.
"""

import asyncio
import json
import sys

import pytest

pytest.importorskip("mcp.client.stdio")

from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def _roundtrip() -> dict:
    params = StdioServerParameters(command=sys.executable, args=["-m", "ledgerlens.mcp_server"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = sorted(t.name for t in listed.tools)
            call = await session.call_tool("search_transactions", {"category": "Income", "limit": 1})
            payload = json.loads(call.content[0].text)
            return {"names": names, "payload": payload}


def test_stdio_roundtrip():
    result = asyncio.run(_roundtrip())
    assert {
        "budget_status",
        "detect_subscriptions",
        "search_transactions",
        "spending_by_category",
    } <= set(result["names"])
    # Egress masking survives the full protocol round-trip.
    assert result["payload"]["transactions"][0]["account"].startswith("****")
