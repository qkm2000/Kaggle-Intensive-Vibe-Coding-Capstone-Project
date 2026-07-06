"""Shared response type returned by both orchestrator implementations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentResponse:
    """A concierge answer.

    Attributes:
        agent: which specialist produced the answer (routing is observable).
        text: the human-facing natural-language reply.
        data: the raw structured tool output backing the reply (for
              transparency / the UI / assertions in tests).
    """

    agent: str
    text: str
    data: dict = field(default_factory=dict)
