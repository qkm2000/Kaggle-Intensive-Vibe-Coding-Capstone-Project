"""Tests for the pure analytics engine (deterministic, exact values)."""

import datetime as dt

from ledgerlens import finance


def test_spending_by_category_excludes_income(sample_txns):
    breakdown = finance.spending_by_category(sample_txns)
    assert breakdown["Shopping"] == 1200.00
    assert breakdown["Groceries"] == 170.00
    assert breakdown["Entertainment"] == round(15.99 * 3, 2)
    assert "Income" not in breakdown  # positive amounts are not spend


def test_spending_by_category_is_descending(sample_txns):
    amounts = list(finance.spending_by_category(sample_txns).values())
    assert amounts == sorted(amounts, reverse=True)


def test_summarize(sample_txns):
    s = finance.summarize(sample_txns)
    assert s["total_income"] == 3000.00
    assert s["total_spend"] == round(15.99 * 3 + 170.00 + 1200.00, 2)
    assert s["net"] == round(s["total_income"] - s["total_spend"], 2)
    assert s["transaction_count"] == 7


def test_date_window_filters(sample_txns):
    jan_only = finance.summarize(
        sample_txns, start=dt.date(2026, 1, 1), end=dt.date(2026, 1, 31)
    )
    # Jan: Netflix -15.99, groceries -80, income +3000
    assert jan_only["total_spend"] == round(15.99 + 80.00, 2)
    assert jan_only["total_income"] == 3000.00


def test_detect_subscriptions_flags_recurring_only(sample_txns):
    subs = finance.detect_recurring_subscriptions(sample_txns, min_occurrences=3)
    merchants = {s.merchant for s in subs}
    assert "Netflix" in merchants  # 3 distinct months, stable amount
    assert "FreshMart" not in merchants  # only 2 months -> below threshold
    assert "TechWorld" not in merchants  # one-off large purchase


def test_detected_subscription_fields(sample_txns):
    (netflix,) = [
        s
        for s in finance.detect_recurring_subscriptions(sample_txns)
        if s.merchant == "Netflix"
    ]
    assert netflix.monthly_amount == 15.99
    assert netflix.occurrences == 3
    assert netflix.annualized == round(15.99 * 12, 2)


def test_budget_status_latest_month(sample_txns):
    budgets = {"Shopping": 200.0, "Entertainment": 120.0}
    lines = finance.budget_status(sample_txns, budgets)  # latest month = 2026-03
    shopping = next(line for line in lines if line.category == "Shopping")
    assert shopping.spent == 1200.00
    assert shopping.over_budget is True
    assert shopping.remaining == round(200.0 - 1200.0, 2)
    # Most over-budget category should be first in the returned ordering.
    assert lines[0].category == "Shopping"
