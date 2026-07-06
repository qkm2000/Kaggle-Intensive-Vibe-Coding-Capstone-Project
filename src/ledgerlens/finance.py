"""Pure financial analytics.

Every function here takes a list of :class:`~ledgerlens.models.Transaction`
and returns plain data. No I/O, no globals, no randomness -> deterministic and
directly unit-testable. All money is rounded to cents on the way out.
"""

from __future__ import annotations

import datetime as dt
import statistics
from collections import defaultdict

from .models import BudgetLine, Subscription, Transaction


def _in_range(
    txn: Transaction, start: dt.date | None, end: dt.date | None
) -> bool:
    if start and txn.date < start:
        return False
    if end and txn.date > end:
        return False
    return True


def filter_transactions(
    txns: list[Transaction],
    *,
    query: str = "",
    category: str | None = None,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> list[Transaction]:
    """Filter by case-insensitive substring, category and date range."""
    q = query.lower().strip()
    cat = category.lower().strip() if category else None
    out = []
    for t in txns:
        if not _in_range(t, start, end):
            continue
        if cat and t.category.lower() != cat:
            continue
        if q and q not in t.description.lower() and q not in t.merchant.lower():
            continue
        out.append(t)
    # Newest first — most useful default ordering for "show me my ..." queries.
    return sorted(out, key=lambda t: t.date, reverse=True)


def spending_by_category(
    txns: list[Transaction],
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, float]:
    """Total *outflow* per category (descending), for the date window."""
    totals: dict[str, float] = defaultdict(float)
    for t in txns:
        if t.is_expense and _in_range(t, start, end):
            totals[t.category] += t.outflow
    return {
        cat: round(amt, 2)
        for cat, amt in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    }


def summarize(
    txns: list[Transaction],
    *,
    start: dt.date | None = None,
    end: dt.date | None = None,
) -> dict[str, float | int]:
    """Headline totals for a window: spend, income, net, transaction count."""
    scoped = [t for t in txns if _in_range(t, start, end)]
    spend = round(sum(t.outflow for t in scoped), 2)
    income = round(sum(t.inflow for t in scoped), 2)
    return {
        "total_spend": spend,
        "total_income": income,
        "net": round(income - spend, 2),
        "transaction_count": len(scoped),
    }


def _month_key(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def detect_recurring_subscriptions(
    txns: list[Transaction],
    *,
    min_occurrences: int = 3,
    amount_tolerance: float = 0.15,
) -> list[Subscription]:
    """Detect likely subscriptions: same merchant, stable amount, monthly-ish.

    Heuristic (intentionally simple and explainable):

    1. Group expenses by merchant.
    2. Within a merchant, cluster charges whose magnitude is within
       ``amount_tolerance`` (fractional) of the group's median.
    3. A cluster spanning ``>= min_occurrences`` *distinct months* is reported
       as a subscription, priced at the median charge.

    Returns subscriptions sorted by annualized cost (most expensive first) so
    the "cancel this to save the most" candidate is on top.
    """
    by_merchant: dict[str, list[Transaction]] = defaultdict(list)
    for t in txns:
        if t.is_expense:
            by_merchant[t.merchant].append(t)

    subs: list[Subscription] = []
    for merchant, charges in by_merchant.items():
        if len(charges) < min_occurrences:
            continue
        amounts = [c.outflow for c in charges]
        median = statistics.median(amounts)
        if median <= 0:
            continue
        # Keep charges close to the median (filters out one-off large buys).
        cluster = [
            c for c in charges if abs(c.outflow - median) <= amount_tolerance * median
        ]
        distinct_months = {_month_key(c.date) for c in cluster}
        if len(distinct_months) < min_occurrences:
            continue
        dates = sorted(c.date for c in cluster)
        subs.append(
            Subscription(
                merchant=merchant,
                category=cluster[0].category,
                monthly_amount=round(median, 2),
                occurrences=len(cluster),
                first_date=dates[0],
                last_date=dates[-1],
            )
        )
    return sorted(subs, key=lambda s: s.annualized, reverse=True)


def budget_status(
    txns: list[Transaction],
    budgets: dict[str, float],
    *,
    month: str | None = None,
) -> list[BudgetLine]:
    """Budget vs. actual per category for ``month`` (``YYYY-MM``).

    If ``month`` is ``None`` the most recent month present in the data is used.
    Categories with a budget but no spend still appear (spent = 0).
    """
    expenses = [t for t in txns if t.is_expense]
    if not expenses and not budgets:
        return []
    if month is None:
        month = max(_month_key(t.date) for t in txns) if txns else None

    spent: dict[str, float] = defaultdict(float)
    for t in expenses:
        if month is None or _month_key(t.date) == month:
            spent[t.category] += t.outflow

    categories = set(budgets) | set(spent)
    lines = [
        BudgetLine(
            category=cat,
            budget=round(budgets.get(cat, 0.0), 2),
            spent=round(spent.get(cat, 0.0), 2),
        )
        for cat in categories
    ]
    # Most over-budget first (largest overspend at the top).
    return sorted(lines, key=lambda b: b.spent - b.budget, reverse=True)
