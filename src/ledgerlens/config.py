"""Runtime configuration.

Everything that could vary between environments (data location, model name,
API key, budgets) is resolved here so the rest of the code never reads
``os.environ`` directly. Secrets are read from the environment / a gitignored
``.env`` file and are *never* hard-coded (submission rule: no keys in code).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # python-dotenv is a declared dependency, but stay import-safe regardless.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - defensive only
    pass

# repo_root/src/ledgerlens/config.py -> parents[2] == repo root
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "transactions.csv"

# Monthly budget targets (USD) per spending category. These would normally be
# user-configured; kept here as sensible defaults for the demo.
DEFAULT_BUDGETS: dict[str, float] = {
    "Groceries": 500.0,
    "Dining": 250.0,
    "Transport": 150.0,
    "Entertainment": 120.0,
    "Shopping": 200.0,
    "Utilities": 300.0,
    "Subscriptions": 60.0,
    "Health": 150.0,
}


@dataclass(frozen=True)
class Settings:
    """Immutable, fully-resolved runtime settings."""

    data_path: Path
    model: str
    google_api_key: str | None
    budgets: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BUDGETS))
    # Optional OpenAI-compatible endpoint (e.g. a local vLLM server). When set,
    # LedgerLens routes through the local-LLM concierge instead of Gemini.
    llm_base_url: str | None = None
    llm_api_key: str | None = None

    @property
    def use_real_llm(self) -> bool:
        """True when a Gemini key is present -> use the live ADK agents.

        This single flag is what lets LedgerLens be *key-optional*: no key
        simply routes callers to the deterministic fallback orchestrator.
        """
        return bool(self.google_api_key)

    @property
    def use_local_llm(self) -> bool:
        """True when an OpenAI-compatible base URL is configured.

        Takes precedence over Gemini in the CLI so you can point LedgerLens at
        a private/local model with no cloud key at all.
        """
        return bool(self.llm_base_url)


def load_settings() -> Settings:
    """Build :class:`Settings` from environment variables with safe defaults."""
    data_path = Path(os.environ.get("LEDGERLENS_DATA_PATH", DEFAULT_DATA_PATH))
    model = os.environ.get("LEDGERLENS_MODEL", "gemini-2.0-flash")
    # Accept either GOOGLE_API_KEY or GEMINI_API_KEY; treat blank as unset.
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    api_key = api_key.strip() if api_key else None
    # OpenAI-compatible local endpoint (base URL must include the /v1 suffix).
    llm_base_url = os.environ.get("LEDGERLENS_LLM_BASE_URL")
    llm_base_url = llm_base_url.strip() if llm_base_url else None
    llm_api_key = os.environ.get("LEDGERLENS_LLM_API_KEY")
    llm_api_key = llm_api_key.strip() if llm_api_key else None
    return Settings(
        data_path=data_path,
        model=model,
        google_api_key=api_key or None,
        llm_base_url=llm_base_url or None,
        llm_api_key=llm_api_key or None,
    )
