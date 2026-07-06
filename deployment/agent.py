"""ADK deployment entry point.

Google ADK tooling (`adk web`, `adk api_server`, `adk deploy cloud_run`) looks
for a package that exposes a module-level ``root_agent``. This module provides
exactly that by delegating to the tested factory in ``ledgerlens.agents``.

    adk deploy cloud_run --project <P> --region <R> deployment

See ``docs/DEPLOY.md`` for the full walkthrough.
"""

from __future__ import annotations

from ledgerlens.agents import build_agent

# Construct the orchestrator + specialists, wired to the MCP server (stdio).
# Construction performs no network I/O; a GOOGLE_API_KEY is only needed at
# request time on the deployed service.
root_agent = build_agent(use_mcp=True)
