"""Run LedgerLens against an OpenAI-compatible *local* LLM (e.g. a vLLM server).

Why not plain "ADK on a local model"? Many self-hosted models don't emit
OpenAI-standard ``tool_calls`` — they return tool calls as free text — so ADK's
function-calling and agent-transfer flow can't drive them reliably. Instead we
use a robust hybrid that suits a local model's strengths:

    1. ROUTE    - the LLM classifies the question into a specialist, with a
                  deterministic keyword fallback if the reply is unexpected.
    2. EXECUTE  - the chosen specialist runs the *real* tool over the ledger
                  (deterministic, validated, PII-masked — the tested path).
    3. COMPOSE  - the LLM writes the final answer grounded ONLY in that tool
                  output, so figures are never hallucinated.

Tool use stays reliable; the local model does the language work. This backend
satisfies the same ``ask(question) -> AgentResponse`` contract as the ADK and
offline backends, so the CLI treats them identically.
"""

from __future__ import annotations

import json
import re

from .config import Settings
from .orchestrator import Orchestrator, classify_intent
from .response import AgentResponse
from .tools import FinanceTools

_VALID_INTENTS = ("spending", "subscriptions", "budget")

# Reasoning models (like the target vLLM model) may emit <think>...</think>
# blocks in the content. Strip them so they never reach the user.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def strip_reasoning(text: str) -> str:
    """Remove <think> reasoning blocks (matched or dangling) from model output."""
    text = _THINK_BLOCK.sub("", text)
    if "</think>" in text:  # dangling close tag with no opener -> keep the tail
        text = text.rsplit("</think>", 1)[-1]
    return text.replace("<think>", "").strip()


# Extra rules for the subscription specialist so the model distinguishes a
# cancellable subscription from an essential bill (and never suggests dropping
# the electricity). Relies on the 'kind' field the tool attaches to each item.
_SUBSCRIPTION_GUIDANCE = (
    " Each item has a 'kind' field. Items with kind 'essential' (utilities, "
    "groceries, transport, insurance, housing) are recurring BILLS the user "
    "cannot simply cancel — NEVER recommend dropping these; only note them as "
    "fixed costs if relevant. Only ever recommend cancelling items with kind "
    "'discretionary' (e.g. streaming, music, news, cloud storage, gym, "
    "software). Respect anything the user says they want to keep, and compute "
    "any savings figure from the discretionary items only."
)


class LocalLlmClient:
    """A thin OpenAI-compatible chat client over LiteLLM.

    LiteLLM's ``openai/<model>`` provider targets any OpenAI-compatible server
    (vLLM, LM Studio, Ollama, LiteLLM proxy, ...) given an ``api_base`` that
    includes the ``/v1`` suffix.
    """

    def __init__(self, base_url: str, api_key: str | None, model: str):
        self.base_url = base_url
        self.api_key = api_key or "not-needed"
        self.model = model

    def chat(self, messages: list[dict], *, max_tokens: int = 400, temperature: float = 0.2) -> str:
        import litellm  # imported lazily so the rest of the package needs no LLM deps

        litellm.drop_params = True  # tolerate sampling params the server rejects
        resp = litellm.completion(
            model=f"openai/{self.model}",
            api_base=self.base_url,
            api_key=self.api_key,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return strip_reasoning(resp.choices[0].message.content or "")


class LocalLlmConcierge:
    """Hybrid concierge backed by a local OpenAI-compatible model."""

    def __init__(self, tools: FinanceTools, settings: Settings, *, client: LocalLlmClient | None = None):
        self._tools = tools
        self._orch = Orchestrator(tools)  # reuse specialists + secured tool wiring
        # ``client`` is injectable so tests can run without a network/model.
        self._client = client or LocalLlmClient(
            settings.llm_base_url, settings.llm_api_key, settings.model
        )

    def _route(self, question: str) -> str:
        """LLM intent classification with a keyword-based safety net."""
        prompt = [
            {
                "role": "system",
                "content": (
                    "Classify the user's personal-finance question into exactly one "
                    "label: 'spending' (past spending / transactions), 'subscriptions' "
                    "(recurring charges / saving money), or 'budget' (budgets / "
                    "overspending). Reply with ONLY the label, nothing else."
                ),
            },
            {"role": "user", "content": question},
        ]
        try:
            raw = self._client.chat(prompt, max_tokens=8, temperature=0).lower()
        except Exception:
            return classify_intent(question)
        for intent in _VALID_INTENTS:
            if intent in raw:
                return intent
        return classify_intent(question)  # model went off-script -> keyword fallback

    def _compose(self, question: str, agent_name: str, data: dict) -> str:
        """Ask the model to phrase an answer grounded strictly in tool output."""
        system = (
            "You are LedgerLens, a friendly and concise personal-finance "
            "concierge. Answer the user's question using ONLY the JSON data "
            "provided. All amounts are USD. Never invent numbers or "
            "transactions that are not in the data. If the data is empty, "
            "say you couldn't find anything relevant."
        )
        # The subscription specialist needs the essential-vs-discretionary rules.
        if agent_name.startswith("SubscriptionHunter"):
            system += _SUBSCRIPTION_GUIDANCE
        prompt = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": (
                    f"Question: {question}\n\n"
                    f"Data from the {agent_name} tool (JSON):\n{json.dumps(data, indent=2)}"
                ),
            },
        ]
        # Generous cap so long tabular answers aren't truncated mid-table.
        return self._client.chat(prompt, max_tokens=800, temperature=0.3)

    def ask(self, question: str) -> AgentResponse:
        intent = self._route(question)
        agent = self._orch.agents[intent]
        grounded = agent.handle(question, self._tools)  # runs the real, secured tool
        try:
            text = self._compose(question, agent.name, grounded.data)
        except Exception as exc:  # network / server hiccup -> deterministic answer
            text = f"{grounded.text}\n\n(note: local LLM unavailable: {exc})"
        if not text.strip():
            text = grounded.text
        return AgentResponse(agent=f"{agent.name} (LocalLLM)", text=text, data=grounded.data)
