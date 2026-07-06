"""Tests for the tool layer: input validation + egress PII masking."""

import re

import pytest

from ledgerlens.security import ValidationError

_LONG_DIGITS = re.compile(r"\d{7,}")


def test_search_masks_account_numbers(real_tools):
    result = real_tools.search_transactions(category="Income", limit=5)
    assert result["count"] > 0
    for txn in result["transactions"]:
        assert txn["account"].startswith("****")
        # No raw long digit-run should ever appear in an account field.
        assert not _LONG_DIGITS.search(txn["account"])


def test_search_redacts_pii_in_description(real_tools):
    # The 'P2P Pay' adversarial row embeds a card number in its memo.
    result = real_tools.search_transactions(query="P2P")
    assert result["count"] >= 1
    desc = result["transactions"][0]["description"]
    assert "4111 1111 1111 2468" not in desc
    assert "****2468" in desc


def test_search_rejects_bad_date(real_tools):
    with pytest.raises(ValidationError):
        real_tools.search_transactions(start_date="not-a-date")


def test_detect_subscriptions_reports_savings(real_tools):
    result = real_tools.detect_subscriptions()
    assert result["count"] >= 3  # Netflix, Spotify, Adobe, CloudDrive, NYT, PureGym
    assert result["total_annual"] > 0
    merchants = {s["merchant"] for s in result["subscriptions"]}
    assert "Netflix" in merchants
    # A one-off big purchase must not be mistaken for a subscription.
    assert "TechWorld" not in merchants


def test_budget_status_shape(real_tools):
    result = real_tools.budget_status()
    assert result["month"] == "latest"
    assert isinstance(result["lines"], list) and result["lines"]
    line = result["lines"][0]
    assert {"category", "budget", "spent", "remaining", "pct_used", "over_budget"} <= set(line)
