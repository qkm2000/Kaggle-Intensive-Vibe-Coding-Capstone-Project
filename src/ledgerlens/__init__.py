"""LedgerLens: a personal finance concierge.

Architecture (see docs/architecture.md):

    User
     |
     v
  Orchestrator agent  ── routes intent to one of three specialists ──┐
     |                                                               |
     +-- AnalystAgent            (spending questions)                |
     +-- SubscriptionHunterAgent (finds recurring charges)           |
     +-- AdvisorAgent            (budget coaching)                   |
                                                                     |
                        all specialists call the same domain tools --+
                                          |
                                          v
                              Custom MCP server (mcp_server.py)
                                          |
                                          v
                     Security layer -> finance analytics -> data store (CSV)

There are two interchangeable orchestrator implementations behind one
interface (``ask(question) -> AgentResponse``):

* ``ledgerlens.agents``       - the real Google ADK / Gemini multi-agent app.
* ``ledgerlens.orchestrator`` - a deterministic, key-free fallback used for
                                offline demos and the test-suite.
"""

__version__ = "0.1.0"
