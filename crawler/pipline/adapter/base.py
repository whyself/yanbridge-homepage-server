"""适配器抽象基类。

每个数据源实现一个适配器：
  1. extract()       — 从原始数据提取规范化字段
  2. build_llm_prompt() — 构建该数据源专用的 LLM prompt
  3. to_post()        — 组合 extracted + LLMResult → Post
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import LLMResult, Post, RawRecord, SourceType


class AbstractSourceAdapter(ABC):
    """将特定数据源的原始数据转换为统一 Post 结构。"""

    source_type: SourceType  # 子类必须定义

    # ------------------------------------------------------------------
    # 子类必须实现
    # ------------------------------------------------------------------

    @abstractmethod
    def extract(self, raw: RawRecord) -> dict:
        """从 RawRecord.raw_data 提取规范化的中间字段 dict。"""

    @abstractmethod
    def build_llm_prompt(self, extracted: dict) -> tuple[str, str]:
        """构建 (system_prompt, user_prompt)。每个数据源的 prompt 需求不同。"""

    @abstractmethod
    def to_post(
        self, raw: RawRecord, extracted: dict, llm_result: LLMResult,
        rewritten_content: str | None = None,
    ) -> Post:
        """组合 extracted + LLMResult → Post。rewritten_content 为改写后的正文。"""

    # ------------------------------------------------------------------
    # 可选覆盖
    # ------------------------------------------------------------------

    def needs_ocr(self, extracted: dict) -> bool:
        """是否需要 OCR。默认 False。XHS 图集类帖子覆盖为 True。"""
        return False

    def build_dedupe_key(self, extracted: dict) -> str:
        """生成 dedupe_key。子类必须覆盖。"""
        raise NotImplementedError

    def build_content_prompt(self, extracted: dict) -> tuple[str, str] | None:
        """构建 content 改写 prompt。返回 None 表示不需要改写。

        默认返回 None。XHS 适配器在 OCR 后需要改写 content，
        将 OCR 文字融入正文，输出合法 markdown。
        """
        return None

    def build_frontmatter(self, post: Post) -> str:
        """生成 content 的 frontmatter。"""
        return f"---\ncategory: {post.category}\n---\n\n"
