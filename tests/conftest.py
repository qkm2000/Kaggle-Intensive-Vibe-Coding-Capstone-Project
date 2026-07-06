"""Shared pytest fixtures.

A tiny, hand-built ledger keeps the analytics tests exact and readable, while
``real_tools`` loads the bundled sample CSV to exercise the full I/O + security
path end to end.
"""

from __future__ import annotations

import datetime as dt

import pytest

from ledgerlens.config import DEFAULT_BUDGETS, DEFAULT_DATA_PATH
from ledgerlens.data_store import TransactionStore
from ledgerlens.models import Transaction
from ledgerlens.tools import FinanceTools

CHECKING = "4111111111111234"
SAVINGS = "5500005555555678"


def _t(id_, date, desc, merchant, amount, category, account=CHECKING) -> Transaction:
    return Transaction(id_, dt.date.fromisoformat(date), desc, merchant, amount, category, account)


@pytest.fixture
def sample_txns() -> list[Transaction]:
    """7 transactions: a 3-month Netflix subscription, a 2-month grocery run
    (below the recurrence threshold), income, and a one-off big purchase."""
    return [
        _t("1", "2026-01-03", "Netflix Standard", "Netflix", -15.99, "Entertainment"),
        _t("2", "2026-02-03", "Netflix Standard", "Netflix", -15.99, "Entertainment"),
        _t("3", "2026-03-03", "Netflix Standard", "Netflix", -15.99, "Entertainment"),
        _t("4", "2026-01-10", "Weekly groceries", "FreshMart", -80.00, "Groceries"),
        _t("5", "2026-02-10", "Weekly groceries", "FreshMart", -90.00, "Groceries"),
        _t("6", "2026-01-25", "Monthly salary", "Acme", 3000.00, "Income", SAVINGS),
        _t("7", "2026-03-21", "Laptop", "TechWorld", -1200.00, "Shopping"),
    ]


@pytest.fixture
def store(sample_txns) -> TransactionStore:
    return TransactionStore(sample_txns)


@pytest.fixture
def tools(store) -> FinanceTools:
    return FinanceTools(store, DEFAULT_BUDGETS)


@pytest.fixture
def real_store() -> TransactionStore:
    """The bundled sample ledger loaded through the real CSV path."""
    return TransactionStore.from_csv(DEFAULT_DATA_PATH)


@pytest.fixture
def real_tools(real_store) -> FinanceTools:
    return FinanceTools(real_store, DEFAULT_BUDGETS)
