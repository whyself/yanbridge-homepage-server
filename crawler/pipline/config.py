"""Pipeline 配置，从环境变量和 .env 文件读取。"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """自动加载 pipline 目录下的 .env 文件。"""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return  # python-dotenv 未安装，跳过

    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)


def _parse_database_url(url: str) -> str:
    """将 SQLAlchemy 风格的 DATABASE_URL 转为 psycopg2 兼容格式。

    postgresql+psycopg://user:pass@host:port/db?sslmode=disable
    → postgresql://user:pass@host:port/db?sslmode=disable
    """
    return re.sub(r"^postgresql\+[^:]+://", "postgresql://", url)


def _default_media_root() -> str:
    """Return the shared XHS media directory used by xhs-db and pipline."""
    return str(Path(__file__).resolve().parents[1] / "xhs-db" / "datas" / "raw_media")


# 模块加载时自动读取 .env
_load_dotenv()


@dataclass
class PipelineConfig:
    """流水线全局配置。"""

    # --- PostgreSQL (读写: xhs_notes 读, posts 写) ---
    database_url: str = field(
        default_factory=lambda: _parse_database_url(
            os.environ.get(
                "DATABASE_URL",
                "postgresql://postgres:postgres@localhost:5432/yanbridge",
            )
        )
    )

    # --- LLM ---
    deepseek_api_key: str = field(
        default_factory=lambda: os.environ.get("DEEPSEEK_API_KEY", "")
    )
    deepseek_api_url: str = "https://api.deepseek.com/chat/completions"
    deepseek_model: str = "deepseek-v4-flash"

    # --- 请求控制 ---
    request_interval: float = 0.5
    max_retries: int = 3
    retry_delay: float = 5.0

    # --- OCR ---
    media_root: str = field(
        default_factory=lambda: os.environ.get("MEDIA_ROOT") or _default_media_root()
    )

    # --- Agent tools / CRW ---
    crw_api_url: str = field(
        default_factory=lambda: os.environ.get("CRW_API_URL", "http://localhost:3000").rstrip("/")
    )
    crw_api_key: str = field(default_factory=lambda: os.environ.get("CRW_API_KEY", ""))
    crw_timeout: float = field(
        default_factory=lambda: float(os.environ.get("CRW_TIMEOUT", "30"))
    )

    # PydanticAI model string, e.g. "openai:gpt-4o-mini".
    agent_model: str = field(default_factory=lambda: os.environ.get("AGENT_MODEL", ""))

    @property
    def media_root_path(self) -> Path:
        return Path(self.media_root)
