"""Data access layer: load transactions from CSV and expose a query surface.

Two responsibilities live here and nowhere else:

* Parsing the CSV into typed :class:`Transaction` objects.
* Applying *ingress* security: every memo is run through
  :func:`security.sanitize_memo` as it enters the system, so attacker-controlled
  text is neutralised once, at the boundary, rather than at every read site.
"""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from . import finance
from .models import BudgetLine, Subscription, Transaction
from .security import sanitize_memo

REQUIRED_COLUMNS = {"id", "date", "description", "merchant", "amount", "category", "account"}


def load_transactions(path: str | Path) -> list[Transaction]:
    """Load and validate transactions from a CSV file.

    Raises ``FileNotFoundError`` if the file is missing and ``ValueError`` if
    the header is malformed — we fail loudly on bad data rather than silently
    returning a partial ledger.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"transactions file not found: {path}")

    txns: list[Transaction] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        for row in reader:
            txns.append(
                Transaction(
                    id=row["id"].strip(),
                    date=dt.date.fromisoformat(row["date"].strip()),
                    # INGRESS SECURITY: neutralise prompt-injection in memos now.
                    description=sanitize_memo(row["description"]),
                    merchant=row["merchant"].strip(),
                    amount=float(row["amount"]),
                    category=row["category"].strip(),
                    account=row["account"].strip(),
                )
            )
    return txns


class TransactionStore:
    """In-memory ledger with a small, deliberate query surface.

    The store binds a transaction list to the pure functions in ``finance`` and
    is the single object the tool layer talks to. Kept read-only on purpose:
    the concierge can *analyse* money but never *move* it (see README security
    notes) — there are no mutating methods here.
    """

    def __init__(self, transactions: list[Transaction]):
        self._txns = list(transactions)

    @classmethod
    def from_csv(cls, path: str | Path) -> "TransactionStore":
        return cls(load_transactions(path))

    def __len__(self) -> int:
        return len(self._txns)

    @property
    def transactions(self) -> list[Transaction]:
        return list(self._txns)

    # --- query methods (thin, security-agnostic; egress masking is done in the
    #     tool layer so both MCP and ADK paths get it uniformly) ------------- #

    def search(
        self,
        *,
        query: str = "",
        category: str | None = None,
        start: dt.date | None = None,
        end: dt.date | None = None,
        limit: int = 20,
    ) -> list[Transaction]:
        results = finance.filter_transactions(
            self._txns, query=query, category=category, start=start, end=end
        )
        return results[:limit]

    def spending_by_category(
        self, *, start: dt.date | None = None, end: dt.date | None = None
    ) -> dict[str, float]:
        return finance.spending_by_category(self._txns, start=start, end=end)

    def summarize(
        self, *, start: dt.date | None = None, end: dt.date | None = None
    ) -> dict[str, float | int]:
        return finance.summarize(self._txns, start=start, end=end)

    def detect_subscriptions(
        self, *, min_occurrences: int = 3
    ) -> list[Subscription]:
        return finance.detect_recurring_subscriptions(
            self._txns, min_occurrences=min_occurrences
        )

    def budget_status(
        self, budgets: dict[str, float], *, month: str | None = None
    ) -> list[BudgetLine]:
        return finance.budget_status(self._txns, budgets, month=month)
