"""Tests for the deterministic multi-agent orchestrator (routing + answers)."""

import pytest

from ledgerlens.orchestrator import Orchestrator, classify_intent


@pytest.mark.parametrize(
    "question,intent",
    [
        ("What are my recurring subscriptions?", "subscriptions"),
        ("How can I save money?", "subscriptions"),
        ("Am I over budget this month?", "budget"),
        ("Can I afford this?", "budget"),
        ("How much did I spend on groceries?", "spending"),
        ("Show me my transactions", "spending"),
    ],
)
def test_classify_intent(question, intent):
    assert classify_intent(question) == intent


def test_routes_to_subscription_hunter(tools):
    resp = Orchestrator(tools).ask("What subscriptions am I paying for?")
    assert resp.agent == "SubscriptionHunter"
    assert resp.data["count"] >= 1
    assert "Netflix" in resp.text


def test_routes_to_budget_advisor(tools):
    resp = Orchestrator(tools).ask("Am I over budget?")
    assert resp.agent == "BudgetAdvisor"
    assert "Budget status" in resp.text


def test_routes_to_analyst_with_category(tools):
    resp = Orchestrator(tools).ask("How much did I spend on groceries?")
    assert resp.agent == "Analyst"
    assert "Groceries" in resp.text


def test_routes_to_analyst_general(tools):
    resp = Orchestrator(tools).ask("Give me an overview of my spending")
    assert resp.agent == "Analyst"
    assert "Top categories" in resp.text


def test_route_returns_agent_object(tools):
    orch = Orchestrator(tools)
    assert orch.route("cancel a subscription").name == "SubscriptionHunter"
