"""Configuration for the standalone homepage agent."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


def load_env(env_file: str | None = None) -> None:
    """Load .env from the server root unless an explicit file is provided."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return

    path = Path(env_file) if env_file else Path(__file__).resolve().parents[1] / ".env"
    if path.exists():
        load_dotenv(path, override=True)


def _parse_database_url(url: str) -> str:
    return re.sub(r"^postgresql\+[^:]+://", "postgresql://", url)


@dataclass
class AgentConfig:
    """Small config object; no dependency on the old pipeline config."""

    database_url: str = field(
        default_factory=lambda: _parse_database_url(
            os.environ.get("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/yanbridge")
        )
    )
    crw_api_url: str = field(default_factory=lambda: os.environ.get("CRW_API_URL", "http://localhost:3000").rstrip("/"))
    crw_api_key: str = field(default_factory=lambda: os.environ.get("CRW_API_KEY", ""))
    crw_timeout: float = field(default_factory=lambda: float(os.environ.get("CRW_TIMEOUT", "30")))

    deepseek_api_key: str = field(default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY", ""))
    deepseek_api_url: str = field(
        default_factory=lambda: os.environ.get("DEEPSEEK_API_URL", "https://api.deepseek.com/chat/completions")
    )
    agent_model: str = field(
        default_factory=lambda: os.environ.get("AGENT_MODEL") or os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
    )

