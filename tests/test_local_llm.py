"""Tests for the local-LLM hybrid concierge.

A fake client stands in for the network so these run offline and deterministically.
They verify the three behaviours that matter: LLM routing, the keyword fallback
when the model goes off-script, grounded composition, and graceful degradation
when the model is unreachable.
"""

from ledgerlens.local_llm import LocalLlmConcierge, strip_reasoning


def test_strip_reasoning_removes_think_blocks():
    assert strip_reasoning("<think>plan the answer</think>Final answer.") == "Final answer."
    # Dangling closing tag (reasoning got truncated) -> keep only the tail.
    assert strip_reasoning("some reasoning</think>The answer") == "The answer"
    assert strip_reasoning("no tags here") == "no tags here"


class FakeClient:
    """Scriptable stand-in for LocalLlmClient.

    Returns ``intent`` for routing calls (identified by the 'Classify' system
    prompt) and ``answer`` for composition calls. Records every call so tests
    can assert what the model was shown.
    """

    def __init__(self, intent="subscriptions", answer="Here is your grounded summary.", raise_on_compose=False):
        self.intent = intent
        self.answer = answer
        self.raise_on_compose = raise_on_compose
        self.calls = []

    def chat(self, messages, **kwargs):
        self.calls.append(messages)
        if "Classify" in messages[0]["content"]:
            return self.intent
        if self.raise_on_compose:
            raise RuntimeError("model offline")
        return self.answer


def _concierge(real_tools, client):
    # settings is unused when a client is injected.
    return LocalLlmConcierge(real_tools, settings=None, client=client)


def test_llm_routing_selects_specialist(real_tools):
    client = FakeClient(intent="subscriptions", answer="You have several subscriptions.")
    resp = _concierge(real_tools, client).ask("what am I paying for?")
    assert resp.agent == "SubscriptionHunter (LocalLLM)"
    assert resp.text == "You have several subscriptions."
    # The tool actually ran and its data backs the answer.
    assert resp.data["count"] >= 3
    # Composition step was shown the real tool JSON (grounding).
    compose_msg = client.calls[1][1]["content"]
    assert "subscriptions" in compose_msg
    # ...and the essential-vs-discretionary rule was injected into the system prompt.
    assert "discretionary" in client.calls[1][0]["content"].lower()


def test_routing_falls_back_to_keywords_on_garbage(real_tools):
    # Model returns an invalid label -> keyword classifier decides instead.
    client = FakeClient(intent="not-a-label", answer="ok")
    resp = _concierge(real_tools, client).ask("how much did I spend on dining?")
    assert resp.agent.startswith("Analyst")


def test_compose_failure_degrades_to_deterministic_text(real_tools):
    client = FakeClient(intent="budget", raise_on_compose=True)
    resp = _concierge(real_tools, client).ask("am I over budget?")
    assert resp.agent == "BudgetAdvisor (LocalLLM)"
    # Falls back to the specialist's deterministic template answer.
    assert "Budget status" in resp.text
    assert "local LLM unavailable" in resp.text


def test_data_is_always_returned(real_tools):
    client = FakeClient(intent="spending", answer="Overview ready.")
    resp = _concierge(real_tools, client).ask("give me an overview")
    assert resp.data  # structured tool output is always attached
