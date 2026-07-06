"""Tests for the MCP server surface.

We import the server module (which builds the tools from the bundled CSV) and
verify the registered tools exist and behave — masking included — without
needing to spawn the stdio transport.
"""

import asyncio

import ledgerlens.mcp_server as srv


def test_expected_tools_registered():
    tools = asyncio.run(srv.mcp.list_tools())
    names = {t.name for t in tools}
    assert {
        "search_transactions",
        "spending_by_category",
        "detect_subscriptions",
        "budget_status",
    } <= names


def test_tool_functions_callable_and_masked():
    out = srv.search_transactions(category="Income", limit=3)
    assert out["count"] > 0
    for txn in out["transactions"]:
        assert txn["account"].startswith("****")


def test_spending_tool_returns_summary():
    out = srv.spending_by_category()
    assert "by_category" in out and "summary" in out
    assert out["summary"]["transaction_count"] > 0


def test_subscriptions_tool():
    out = srv.detect_subscriptions()
    assert out["count"] >= 3
