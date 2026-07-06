"""The domain tool layer — the single source of truth for agent capabilities.

Both entry points call *these* functions:

* ``mcp_server.py``  exposes them as MCP tools (stdio).
* ``agents.py``      wraps them as ADK ``FunctionTool``s (in-process fallback)
                     — while also being able to reach the MCP server itself.

Each tool:
    * validates & clamps its inputs via ``security`` (fail closed),
    * returns a JSON-serialisable ``dict`` (LLM- and MCP-friendly),
    * applies *egress* PII masking so raw account numbers never leave here.

Keeping tools thin wrappers over :class:`TransactionStore` means the same
tested behaviour backs every surface.
"""

from __future__ import annotations

import datetime as dt

from .data_store import TransactionStore
from .models import Transaction
from .security import (
    mask_account,
    redact_pii,
    sanitize_query,
    validate_date,
    validate_limit,
    validate_month,
)


def _txn_to_public_dict(t: Transaction) -> dict:
    """Serialise a transaction for output, masking sensitive fields (egress)."""
    return {
        "id": t.id,
        "date": t.date.isoformat(),
        "description": redact_pii(t.description),
        "merchant": t.merchant,
        "amount": round(t.amount, 2),
        "category": t.category,
        "account": mask_account(t.account),  # ****1234 — never the full number
    }


class FinanceTools:
    """Capabilities exposed to the agents, bound to one transaction store."""

    def __init__(self, store: TransactionStore, budgets: dict[str, float]):
        self._store = store
        self._budgets = dict(budgets)

    # --- tool: search_transactions ------------------------------------- #
    def search_transactions(
        self,
        query: str = "",
        category: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
    ) -> dict:
        """Search transactions by keyword, category and/or date range.

        Args:
            query: case-insensitive substring matched against merchant/memo.
            category: exact category filter (e.g. "Dining").
            start_date / end_date: inclusive ISO ``YYYY-MM-DD`` bounds.
            limit: max rows to return (clamped to 1..100).
        """
        query = sanitize_query(query)
        start = validate_date(start_date, field="start_date")
        end = validate_date(end_date, field="end_date")
        limit = validate_limit(limit)
        rows = self._store.search(
            query=query,
            category=category,
            start=dt.date.fromisoformat(start) if start else None,
            end=dt.date.fromisoformat(end) if end else None,
            limit=limit,
        )
        return {
            "count": len(rows),
            "transactions": [_txn_to_public_dict(t) for t in rows],
        }

    # --- tool: spending_by_category ------------------------------------ #
    def spending_by_category(
        self, start_date: str | None = None, end_date: str | None = None
    ) -> dict:
        """Total spending grouped by category for an optional date window."""
        start = validate_date(start_date, field="start_date")
        end = validate_date(end_date, field="end_date")
        breakdown = self._store.spending_by_category(
            start=dt.date.fromisoformat(start) if start else None,
            end=dt.date.fromisoformat(end) if end else None,
        )
        summary = self._store.summarize(
            start=dt.date.fromisoformat(start) if start else None,
            end=dt.date.fromisoformat(end) if end else None,
        )
        return {"by_category": breakdown, "summary": summary}

    # --- tool: detect_subscriptions ------------------------------------ #
    def detect_subscriptions(self, min_occurrences: int = 3) -> dict:
        """Find recurring charges (likely subscriptions) and their annual cost."""
        min_occ = validate_limit(min_occurrences, default=3)
        subs = self._store.detect_subscriptions(min_occurrences=min_occ)
        total_annual = round(sum(s.annualized for s in subs), 2)
        return {
            "count": len(subs),
            "total_monthly": round(sum(s.monthly_amount for s in subs), 2),
            "total_annual": total_annual,
            "subscriptions": [
                {
                    "merchant": s.merchant,
                    "category": s.category,
                    "monthly_amount": s.monthly_amount,
                    "annualized": s.annualized,
                    "occurrences": s.occurrences,
                    "first_date": s.first_date.isoformat(),
                    "last_date": s.last_date.isoformat(),
                }
                for s in subs
            ],
        }

    # --- tool: budget_status ------------------------------------------- #
    def budget_status(self, month: str | None = None) -> dict:
        """Compare spending against monthly budgets (defaults to latest month)."""
        month = validate_month(month)
        lines = self._store.budget_status(self._budgets, month=month)
        return {
            "month": month or "latest",
            "lines": [
                {
                    "category": b.category,
                    "budget": b.budget,
                    "spent": b.spent,
                    "remaining": b.remaining,
                    "pct_used": b.pct_used,
                    "over_budget": b.over_budget,
                }
                for b in lines
            ],
            "total_over_budget": round(
                sum(b.spent - b.budget for b in lines if b.over_budget), 2
            ),
        }
