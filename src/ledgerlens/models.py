"""Core domain data structures.

Kept deliberately free of any I/O, ADK, or MCP imports so the analytics in
``finance.py`` stay pure and trivially unit-testable.

Amount sign convention (bank-statement style):
    * amount <  0  -> money OUT  (a spend / debit)
    * amount >  0  -> money IN   (income / refund / credit)
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Transaction:
    """A single ledger line."""

    id: str
    date: dt.date
    description: str  # sanitized memo (see security.sanitize_memo)
    merchant: str
    amount: float  # signed; see module docstring
    category: str
    account: str  # raw account identifier; masked before ever leaving a tool

    @property
    def is_expense(self) -> bool:
        return self.amount < 0

    @property
    def outflow(self) -> float:
        """Positive magnitude of a spend, else 0.0."""
        return -self.amount if self.amount < 0 else 0.0

    @property
    def inflow(self) -> float:
        """Positive magnitude of income, else 0.0."""
        return self.amount if self.amount > 0 else 0.0


@dataclass(frozen=True, slots=True)
class Subscription:
    """A detected recurring charge (the 'saved you $X/mo' feature)."""

    merchant: str
    category: str
    monthly_amount: float  # representative (median) charge
    occurrences: int  # number of distinct charges detected
    first_date: dt.date
    last_date: dt.date

    @property
    def annualized(self) -> float:
        return round(self.monthly_amount * 12, 2)


@dataclass(frozen=True, slots=True)
class BudgetLine:
    """Budget vs. actual for one category in one month."""

    category: str
    budget: float
    spent: float

    @property
    def remaining(self) -> float:
        return round(self.budget - self.spent, 2)

    @property
    def over_budget(self) -> bool:
        return self.spent > self.budget

    @property
    def pct_used(self) -> float:
        if self.budget <= 0:
            return 0.0
        return round(self.spent / self.budget * 100, 1)
