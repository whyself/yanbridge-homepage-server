"""Yanbridge 数据流水线。

把不同数据源（XHS/Homepage）的原始 DB 数据，
经过 LLM 分类/提取/清洗，统一写入 posts 表。

Usage:
    python -m crawler.pipline.cli run --source xiaohongshu
    python -m crawler.pipline.cli run --source homepage
"""

from .models import (
    LLMResult,
    Post,
    PostCategory,
    RawRecord,
    SourceType,
)
from .config import PipelineConfig
from .parser import PipelineRunner

__all__ = [
    "PipelineRunner",
    "PipelineConfig",
    "Post",
    "RawRecord",
    "LLMResult",
    "SourceType",
    "PostCategory",
]
