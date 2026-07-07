"""The live Google ADK multi-agent system (used when GOOGLE_API_KEY is set).

Topology (LLM-driven delegation via ADK's ``sub_agents`` transfer mechanism):

    Orchestrator (root LlmAgent)
      ├─ AnalystAgent            -> spending questions
      ├─ SubscriptionHunterAgent -> recurring-charge detection
      └─ AdvisorAgent            -> budget coaching

Tool wiring is pluggable:
    * use_mcp=True  (default): specialists reach the finance tools through our
      custom **MCP server** via ADK's ``McpToolset`` (stdio). This is the
      "ADK agent consuming a custom MCP server" integration.
    * use_mcp=False: the same tools are attached in-process as ``FunctionTool``s
      (used by the construction test so it needs neither a subprocess nor a key).

Security in the agent layer: a ``before_tool_callback`` guardrail inspects every
tool call and blocks any argument carrying a prompt-injection payload — defence
in depth on top of the ingress sanitisation done in ``data_store``.

Importing this module never requires ADK; the heavy imports happen inside the
build functions so the rest of LedgerLens (and the test-suite) works without it.
"""

from __future__ import annotations

import asyncio
import sys

from .config import Settings, load_settings
from .response import AgentResponse
from .security import looks_like_injection
from .tools import FinanceTools

try:  # ADK is an optional extra.
    from google.adk.agents import LlmAgent  # noqa: F401

    ADK_AVAILABLE = True
except Exception:  # pragma: no cover - depends on optional install
    ADK_AVAILABLE = False

APP_NAME = "ledgerlens"


def _require_adk() -> None:
    if not ADK_AVAILABLE:
        raise RuntimeError(
            "google-adk is not installed. Install with: pip install 'ledgerlens[adk]', "
            "or run the key-free orchestrator (ledgerlens.orchestrator.Orchestrator)."
        )


# --------------------------------------------------------------------------- #
# Security guardrail (defence in depth at the tool boundary)
# --------------------------------------------------------------------------- #
def _tool_guardrail(tool, args, tool_context):  # noqa: ANN001 - ADK callback shape
    """Block a tool call if any string argument looks like prompt injection.

    Returning a dict short-circuits execution with that value (ADK contract),
    so a hostile query never reaches the data layer.
    """
    for value in (args or {}).values():
        if isinstance(value, str) and looks_like_injection(value):
            return {
                "error": "blocked_by_guardrail",
                "reason": "input rejected as a suspected prompt-injection attempt",
            }
    return None  # allow


# --------------------------------------------------------------------------- #
# Tool wiring
# --------------------------------------------------------------------------- #
def _function_tools(tools: FinanceTools):
    """Wrap FinanceTools methods as in-process ADK FunctionTools."""
    from google.adk.tools import FunctionTool

    return {
        "search": FunctionTool(tools.search_transactions),
        "spending": FunctionTool(tools.spending_by_category),
        "subscriptions": FunctionTool(tools.detect_subscriptions),
        "budget": FunctionTool(tools.budget_status),
    }


def _mcp_toolset():
    """Connect to the LedgerLens MCP server (stdio) as an ADK toolset."""
    from google.adk.tools.mcp_tool.mcp_toolset import (
        McpToolset,
        StdioConnectionParams,
    )
    from mcp import StdioServerParameters

    # Launch our own server module with the current interpreter so it picks up
    # the same venv/config. The server exposes all four finance tools.
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "ledgerlens.mcp_server"],
            ),
            timeout=30,
        )
    )


# --------------------------------------------------------------------------- #
# Agent construction
# --------------------------------------------------------------------------- #
def build_agent(settings: Settings | None = None, *, tools: FinanceTools | None = None,
                use_mcp: bool = True) -> "LlmAgent":
    """Construct the orchestrator + specialist sub-agents.

    No network call happens here — only object construction — so this is safe
    to unit-test without an API key.
    """
    _require_adk()
    from google.adk.agents import LlmAgent

    settings = settings or load_settings()
    model = settings.model

    if use_mcp:
        # Every specialist reaches the tools through the MCP server. A fresh
        # toolset per agent keeps each subprocess connection independent.
        analyst_tools = [_mcp_toolset()]
        hunter_tools = [_mcp_toolset()]
        advisor_tools = [_mcp_toolset()]
    else:
        ft = tools or _in_process_tools()
        wrapped = _function_tools(ft)
        analyst_tools = [wrapped["search"], wrapped["spending"]]
        hunter_tools = [wrapped["subscriptions"]]
        advisor_tools = [wrapped["budget"]]

    analyst = LlmAgent(
        name="AnalystAgent",
        model=model,
        description="Answers questions about past spending and transactions.",
        instruction=(
            "You analyse the user's transactions. Use spending_by_category for "
            "overviews and search_transactions for specifics. Report figures "
            "clearly in USD. Never invent numbers — only use tool results."
        ),
        tools=analyst_tools,
        before_tool_callback=_tool_guardrail,
    )
    hunter = LlmAgent(
        name="SubscriptionHunterAgent",
        model=model,
        description="Finds recurring charges / subscriptions and savings.",
        instruction=(
            "Call detect_subscriptions and summarise the recurring charges. Use "
            "each item's 'kind' field: NEVER suggest cancelling 'essential' items "
            "(utilities, groceries, transport, insurance) — treat them as fixed "
            "bills. Only recommend dropping 'discretionary' items, highlight the "
            "small easily-forgotten ones, and base savings on discretionary items "
            "only. Respect anything the user says they want to keep."
        ),
        tools=hunter_tools,
        before_tool_callback=_tool_guardrail,
    )
    advisor = LlmAgent(
        name="AdvisorAgent",
        model=model,
        description="Coaches the user on budgets (budget vs. actual).",
        instruction=(
            "Call budget_status and explain where the user is over or under "
            "budget, with one concrete, actionable suggestion."
        ),
        tools=advisor_tools,
        before_tool_callback=_tool_guardrail,
    )

    return LlmAgent(
        name="Orchestrator",
        model=model,
        description="Personal finance concierge that routes to specialists.",
        instruction=(
            "You are LedgerLens, a personal finance concierge. Delegate to the "
            "right specialist:\n"
            "- spending / transaction questions -> AnalystAgent\n"
            "- subscriptions / recurring charges / saving money -> "
            "SubscriptionHunterAgent\n"
            "- budgets / overspending -> AdvisorAgent\n"
            "Never ask the user for account numbers or secrets."
        ),
        sub_agents=[analyst, hunter, advisor],
    )


def _in_process_tools() -> FinanceTools:
    from .data_store import TransactionStore

    settings = load_settings()
    return FinanceTools(TransactionStore.from_csv(settings.data_path), settings.budgets)


class AdkConcierge:
    """Runnable wrapper: ``ask(question) -> AgentResponse`` over the ADK Runner.

    Mirrors :class:`ledgerlens.orchestrator.Orchestrator` so the CLI can use
    either interchangeably. Requires a valid GOOGLE_API_KEY at ``ask`` time.
    """

    def __init__(self, settings: Settings | None = None, *, use_mcp: bool = True):
        _require_adk()
        self.settings = settings or load_settings()
        self.agent = build_agent(self.settings, use_mcp=use_mcp)

    def ask(self, question: str, *, user_id: str = "local", session_id: str = "s1") -> AgentResponse:
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        session_service = InMemorySessionService()
        # create_session is async in ADK 2.x; run it on a throwaway loop.
        asyncio.run(
            session_service.create_session(
                app_name=APP_NAME, user_id=user_id, session_id=session_id
            )
        )
        runner = Runner(agent=self.agent, app_name=APP_NAME, session_service=session_service)
        content = types.Content(role="user", parts=[types.Part(text=question)])

        final_text, author = "", self.agent.name
        for event in runner.run(user_id=user_id, session_id=session_id, new_message=content):
            if event.is_final_response() and event.content and event.content.parts:
                final_text = event.content.parts[0].text or ""
                author = event.author or author
        return AgentResponse(agent=author, text=final_text, data={})
