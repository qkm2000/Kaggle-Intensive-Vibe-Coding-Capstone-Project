"""Deterministic, key-free multi-agent orchestrator.

This mirrors the ADK agent topology (one router + three specialists) but uses
transparent keyword intent-classification instead of an LLM. It exists so that:

    * the full agent *behaviour* can be demonstrated offline with zero API keys,
    * the routing and tool wiring are covered by fast, deterministic tests.

When ``GOOGLE_API_KEY`` is set, ``cli.py`` uses the real Gemini agents in
``agents.py`` instead; both satisfy the same ``ask(question) -> AgentResponse``
contract, so callers don't care which is running.
"""

from __future__ import annotations

from .response import AgentResponse
from .tools import FinanceTools

# Intent -> trigger keywords. Ordered by specificity: subscriptions and budget
# are checked before the catch-all analyst.
_SUBSCRIPTION_WORDS = (
    "subscription",
    "subscriptions",
    "recurring",
    "cancel",
    "save money",
    "paying for",
    "forgotten",
    "wasting",
)
_BUDGET_WORDS = (
    "budget",
    "over budget",
    "overspend",
    "overspending",
    "on track",
    "afford",
    "limit",
)


def classify_intent(question: str) -> str:
    """Map a free-text question to one of: subscriptions | budget | spending."""
    q = question.lower()
    if any(w in q for w in _SUBSCRIPTION_WORDS):
        return "subscriptions"
    if any(w in q for w in _BUDGET_WORDS):
        return "budget"
    return "spending"


def _money(x: float) -> str:
    return f"${x:,.2f}"


class SubscriptionHunterAgent:
    """Specialist: surfaces recurring charges and the savings opportunity."""

    name = "SubscriptionHunter"

    def handle(self, question: str, tools: FinanceTools) -> AgentResponse:
        data = tools.detect_subscriptions()
        subs = data["subscriptions"]
        if not subs:
            return AgentResponse(self.name, "I couldn't find any recurring charges.", data)

        discretionary = [s for s in subs if not s["essential"]]
        essentials = [s for s in subs if s["essential"]]

        lines = [
            f"I found {data['count']} recurring charges totalling "
            f"{_money(data['total_monthly'])}/month ({_money(data['total_annual'])}/year)."
        ]
        if discretionary:
            lines.append(
                f"Discretionary subscriptions you could review "
                f"({_money(data['discretionary_monthly'])}/mo, "
                f"{_money(data['discretionary_annual'])}/yr):"
            )
            for s in discretionary:
                lines.append(
                    f"  • {s['merchant']} — {_money(s['monthly_amount'])}/mo ({s['category']})"
                )
        if essentials:
            names = ", ".join(s["merchant"] for s in essentials)
            lines.append(f"Essential bills (keep — not cancellable): {names}.")
        if discretionary:
            cheapest = min(discretionary, key=lambda s: s["monthly_amount"])
            lines.append(
                f"Tip: '{cheapest['merchant']}' is easy to forget at "
                f"{_money(cheapest['monthly_amount'])}/mo — cancelling it saves "
                f"{_money(cheapest['annualized'])}/year."
            )
        return AgentResponse(self.name, "\n".join(lines), data)


class BudgetAdvisorAgent:
    """Specialist: budget-vs-actual coaching."""

    name = "BudgetAdvisor"

    def handle(self, question: str, tools: FinanceTools) -> AgentResponse:
        data = tools.budget_status()
        lines = [f"Budget status for {data['month']}:"]
        over = [line for line in data["lines"] if line["over_budget"]]
        for line in data["lines"]:
            if line["budget"] == 0 and line["spent"] == 0:
                continue
            flag = "⚠️ OVER" if line["over_budget"] else "ok"
            lines.append(
                f"  • {line['category']}: spent {_money(line['spent'])} of "
                f"{_money(line['budget'])} ({line['pct_used']}%) [{flag}]"
            )
        if over:
            worst = max(over, key=lambda line: line["spent"] - line["budget"])
            lines.append(
                f"You're over budget in {len(over)} categories; the biggest gap "
                f"is {worst['category']} by "
                f"{_money(worst['spent'] - worst['budget'])}."
            )
        else:
            lines.append("Nice — you're within budget in every category.")
        return AgentResponse(self.name, "\n".join(lines), data)


class AnalystAgent:
    """Specialist (default): answers general spending questions."""

    name = "Analyst"

    # Category keywords we recognise inside a free-text question.
    _CATEGORIES = (
        "groceries",
        "dining",
        "transport",
        "entertainment",
        "shopping",
        "utilities",
        "subscriptions",
        "health",
    )

    def _detect_category(self, question: str) -> str | None:
        q = question.lower()
        for cat in self._CATEGORIES:
            if cat in q:
                return cat.capitalize()
        return None

    def handle(self, question: str, tools: FinanceTools) -> AgentResponse:
        category = self._detect_category(question)
        if category:
            # Focused question about one category -> list recent matches.
            data = tools.search_transactions(category=category, limit=50)
            total = round(sum(-t["amount"] for t in data["transactions"] if t["amount"] < 0), 2)
            text = (
                f"You have {data['count']} '{category}' transactions totalling "
                f"{_money(total)}. Most recent:\n"
                + "\n".join(
                    f"  • {t['date']} {t['merchant']} {_money(t['amount'])}"
                    for t in data["transactions"][:5]
                )
            )
            return AgentResponse(self.name, text, data)

        # General question -> category breakdown + headline summary.
        data = tools.spending_by_category()
        summary = data["summary"]
        top = list(data["by_category"].items())[:5]
        text = (
            f"Across {summary['transaction_count']} transactions you spent "
            f"{_money(summary['total_spend'])} and earned "
            f"{_money(summary['total_income'])} (net "
            f"{_money(summary['net'])}). Top categories:\n"
            + "\n".join(f"  • {cat}: {_money(amt)}" for cat, amt in top)
        )
        return AgentResponse(self.name, text, data)


class Orchestrator:
    """Routes a question to the right specialist agent (deterministic)."""

    def __init__(self, tools: FinanceTools):
        self._tools = tools
        self._agents = {
            "subscriptions": SubscriptionHunterAgent(),
            "budget": BudgetAdvisorAgent(),
            "spending": AnalystAgent(),
        }

    @property
    def agents(self) -> dict:
        """The intent -> specialist mapping (reused by the local-LLM backend)."""
        return self._agents

    def route(self, question: str):
        """Return the specialist agent that will handle ``question``."""
        return self._agents[classify_intent(question)]

    def ask(self, question: str) -> AgentResponse:
        return self.route(question).handle(question, self._tools)
