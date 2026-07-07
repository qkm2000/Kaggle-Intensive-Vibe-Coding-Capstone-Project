"""Command-line concierge.

    ledgerlens "how much did I spend on dining?"   # one-shot
    ledgerlens                                       # interactive REPL

Automatically selects the backend:
    * GOOGLE_API_KEY set -> live Gemini ADK multi-agent system (agents.py)
    * otherwise          -> deterministic key-free orchestrator (orchestrator.py)

Both expose ``ask(question) -> AgentResponse``.
"""

from __future__ import annotations

import argparse
import sys

from .config import load_settings
from .data_store import TransactionStore
from .orchestrator import Orchestrator
from .tools import FinanceTools


def _build_backend():
    """Return an object with ``ask(question) -> AgentResponse`` and a label.

    Backend precedence: local OpenAI-compatible LLM -> Gemini ADK -> offline.
    """
    settings = load_settings()
    store = TransactionStore.from_csv(settings.data_path)
    tools = FinanceTools(store, settings.budgets)

    if settings.use_local_llm:
        # Local/self-hosted model (e.g. vLLM). Hybrid: deterministic tools +
        # LLM routing & answer composition. See local_llm.py for the rationale.
        from .local_llm import LocalLlmConcierge

        return LocalLlmConcierge(tools, settings), f"local LLM ({settings.model} @ {settings.llm_base_url})"

    if settings.use_real_llm:
        # Import lazily: only touch ADK when we actually intend to use it.
        from .agents import AdkConcierge

        return AdkConcierge(settings), f"Gemini ADK ({settings.model})"

    return Orchestrator(tools), "offline orchestrator (no API key)"


def _answer(backend, question: str) -> None:
    response = backend.ask(question)
    print(f"\n[{response.agent}]\n{response.text}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ledgerlens", description="Personal finance concierge.")
    parser.add_argument("question", nargs="*", help="A question to ask (omit for interactive mode).")
    args = parser.parse_args(argv)

    backend, label = _build_backend()
    print(f"LedgerLens — backend: {label}")

    if args.question:
        _answer(backend, " ".join(args.question))
        return 0

    # Interactive REPL.
    print("Ask about your finances (Ctrl-D / 'quit' to exit).")
    try:
        while True:
            question = input("> ").strip()
            if question.lower() in {"quit", "exit"}:
                break
            if question:
                _answer(backend, question)
    except (EOFError, KeyboardInterrupt):
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
