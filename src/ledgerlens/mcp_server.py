"""Custom MCP server exposing LedgerLens' finance tools over stdio.

This is a genuine Model Context Protocol server (built on the official ``mcp``
SDK's ``FastMCP``). Any MCP client can drive it:

    * Google ADK via ``MCPToolset`` (see ``agents.py``),
    * Claude Desktop / other MCP hosts,
    * ``mcp dev src/ledgerlens/mcp_server.py`` for the inspector.

Run directly:  ``python -m ledgerlens.mcp_server``  (or ``ledgerlens-mcp``).

The tools are thin pass-throughs to :class:`FinanceTools`, so the exact same
validated, PII-masked behaviour is shared with the in-process ADK path.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .config import load_settings
from .data_store import TransactionStore
from .tools import FinanceTools


def build_tools() -> FinanceTools:
    """Load settings + data and construct the shared tool implementation."""
    settings = load_settings()
    store = TransactionStore.from_csv(settings.data_path)
    return FinanceTools(store, settings.budgets)


# Module-level server so `mcp dev` / `mcp install` can import `mcp`.
mcp = FastMCP("ledgerlens")
_tools = build_tools()


@mcp.tool()
def search_transactions(
    query: str = "",
    category: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
) -> dict:
    """Search transactions by keyword, category and/or ISO date range.

    Account numbers in results are masked to the last four digits.
    """
    return _tools.search_transactions(
        query=query,
        category=category,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@mcp.tool()
def spending_by_category(
    start_date: str | None = None, end_date: str | None = None
) -> dict:
    """Total spending grouped by category, with a headline summary."""
    return _tools.spending_by_category(start_date=start_date, end_date=end_date)


@mcp.tool()
def detect_subscriptions(min_occurrences: int = 3) -> dict:
    """Find recurring charges (likely subscriptions) and their annual cost."""
    return _tools.detect_subscriptions(min_occurrences=min_occurrences)


@mcp.tool()
def budget_status(month: str | None = None) -> dict:
    """Compare spending vs. monthly budgets (defaults to the latest month)."""
    return _tools.budget_status(month=month)


def main() -> None:
    """Console-script entry point: serve over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
