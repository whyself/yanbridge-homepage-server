"""
Pipeline 核心数据模型。

RawRecord → (adapter) → LLMResult → Post → (writer) → posts 表
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class SourceType(StrEnum):
    ZHIHU = "zhihu"
    XIAOHONGSHU = "xiaohongshu"
    PERSONAL_WEBSITE = "personal_website"


class PostCategory(StrEnum):
    MENTOR_RECRUITMENT = "mentor_recruitment"
    STUDENT_APPLICATION = "student_application"
    PROJECT_COOPERATION = "project_cooperation"
    ACADEMIC_EXCHANGE = "academic_exchange"


@dataclass
class RawRecord:
    """从数据源 DB 读取的原始记录，来源无关。"""
    source_type: SourceType
    raw_data: dict[str, Any]


@dataclass
class LLMResult:
    """LLM 处理的结构化输出。"""
    action: str                              # "keep" | "rewrite" | "irrelevant"
    title: str
    category: str | None = None              # PostCategory 值
    university_name: str = ""
    school_name: str = ""
    major_name: str = ""
    summary: str | None = None
    content: str = ""                        # LLM 改写后的招生帖子内容 (markdown)
    raw_response: dict[str, Any] = field(default_factory=dict)


@dataclass
class Post:
    """统一 Post 结构，映射 posts 表。"""
    source_type: SourceType
    post_type: str                           # "crawled_post" | "user_post"
    title: str
    category: str                            # PostCategory 值
    status: str = "published"
    author_user_id: str | None = None
    summary: str | None = None
    content: str | None = None               # Markdown, 含 frontmatter
    university_name: str | None = None
    school_name: str | None = None
    major_name: str | None = None
    source_url: str | None = None
    dedupe_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None
    deleted_at: str | None = None

    def to_db_row(self) -> dict[str, Any]:
        """序列化为 posts 表 INSERT 用的 dict。"""
        import json
        return {
            "source_type": str(self.source_type),
            "post_type": self.post_type,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "author_user_id": self.author_user_id,
            "summary": self.summary,
            "content": self.content,
            "university_name": self.university_name,
            "school_name": self.school_name,
            "major_name": self.major_name,
            "source_url": self.source_url,
            "dedupe_key": self.dedupe_key,
            "metadata": json.dumps(self.metadata, ensure_ascii=False),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
