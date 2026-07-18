"""Homepage (教师主页) 适配器。

从 homepage_raw_page 表字段映射到统一 Post 结构。
"""

from __future__ import annotations

from ..models import LLMResult, Post, PostCategory, RawRecord, SourceType
from .base import AbstractSourceAdapter
SYSTEM_PROMPT = """你是一个高校教师/课题组主页信息抽取助手。

目标：把页面抽取为 teacher_profiles 需要的简单结构。

规则：
1. 不要编造信息；找不到就填空字符串、空数组或 false。
2. action 只表示是否有明确招生信息：有招生/招学生/招实习/招硕博则 keep，否则 irrelevant。
3. teacher_name_cn 中文名；teacher_name_en 英文名。显示名默认使用 teacher_name_cn。
4. evidence 必须是 URL 字符串数组，只放支持判断的页面 URL，不要放文本证据。
5. research_directions 必须是字符串数组。

严格返回 JSON，不要输出其他内容：
{
  "action": "keep|irrelevant",
  "university_name": "",
  "school_name": "",
  "lab_name": "",
  "teacher_name_cn": "",
  "teacher_name_en": "",
  "title": "",
  "email": "",
  "research_directions": [],
  "has_recruitment": false,
  "evidence": ["https://..."],
  "summary": "",
  "category": "mentor_recruitment",
  "content": ""
}
"""


class HomepageAdapter(AbstractSourceAdapter):
    source_type = SourceType.PERSONAL_WEBSITE

    # ------------------------------------------------------------------
    # extract
    # ------------------------------------------------------------------

    def extract(self, raw: RawRecord) -> dict:
        d = raw.raw_data
        return {
            "source_id": d.get("source_id", ""),
            "batch": d.get("batch", ""),
            "university": d.get("university", ""),
            "source_subtype": d.get("source_type", ""),  # 'faculty' | 'lab'
            "name": d.get("name", ""),
            "requested_url": d.get("requested_url", ""),
            "final_url": d.get("final_url", "") or d.get("requested_url", ""),
            "page_title": d.get("page_title", "") or "",
            "markdown": d.get("markdown", "") or "",
            "text": d.get("text", "") or "",
            "content_hash": d.get("content_hash", ""),
            "fetched_at": d.get("fetched_at", ""),
            "http_status": d.get("http_status"),
        }

    # ------------------------------------------------------------------
    # LLM prompt
    # ------------------------------------------------------------------

    def build_llm_prompt(self, extracted: dict) -> tuple[str, str]:
        text_content = extracted["text"]
        # 截断过长内容
        if len(text_content) > 4000:
            text_content = text_content[:4000]

        user_msg = (
            f"URL: {extracted['requested_url']}\n"
            f"页面标题: {extracted['page_title']}\n"
            f"姓名: {extracted['name']}\n"
            f"学校: {extracted['university']}\n"
            f"类型: {extracted['source_subtype']}\n"
            f"\n正文：\n{text_content}"
        )
        return SYSTEM_PROMPT, user_msg

    # ------------------------------------------------------------------
    # to_post
    # ------------------------------------------------------------------

    def to_post(
        self, raw: RawRecord, extracted: dict, llm_result: LLMResult,
        rewritten_content: str | None = None,
    ) -> Post:
        category = llm_result.category or PostCategory.MENTOR_RECRUITMENT
        teacher_name = llm_result.teacher_name_cn or llm_result.teacher_name_en or extracted["name"]
        title = llm_result.title or f"{llm_result.university_name or extracted['university']}{teacher_name}老师主页"

        post = Post(
            source_type=self.source_type,
            post_type="crawled_post",
            title=title,
            category=category,
            status="published",
            author_user_id=None,
            summary=llm_result.summary or llm_result.recruitment_text or "",
            university_name=llm_result.university_name or extracted["university"],
            school_name=llm_result.school_name or None,
            major_name=llm_result.major_name or None,
            source_url=extracted["final_url"] or extracted["requested_url"],
            dedupe_key=self.build_post_dedupe_key(extracted),
            created_at=extracted["fetched_at"],
            updated_at=extracted["fetched_at"],
            deleted_at=None,
        )

        # content: frontmatter + LLM 改写后的招生帖正文 (或原始 markdown 降级)
        body = llm_result.content or rewritten_content or (extracted["markdown"] or "")
        post.content = self.build_frontmatter(post) + body

        # metadata: 原始抓取信息
        post.metadata = {
            "source_id": extracted["source_id"],
            "batch": extracted["batch"],
            "source_subtype": extracted["source_subtype"],  # faculty | lab
            "name": teacher_name,
            "teacher_name": teacher_name,
            "teacher_name_cn": llm_result.teacher_name_cn,
            "teacher_name_en": llm_result.teacher_name_en,
            "lab_name": llm_result.lab_name,
            "email": llm_result.email,
            "research_directions": llm_result.research_directions,
            "has_recruitment": llm_result.has_recruitment,
            "recruitment_text": llm_result.recruitment_text,
            "evidence": llm_result.evidence,
            "requested_url": extracted["requested_url"],
            "final_url": extracted["final_url"],
            "page_title": extracted["page_title"],
            "content_hash": extracted["content_hash"],
            "http_status": extracted["http_status"],
            "raw_version_key": self.build_dedupe_key(extracted),
        }

        return post

    # ------------------------------------------------------------------
    # dedupe
    # ------------------------------------------------------------------

    def build_dedupe_key(self, extracted: dict) -> str:
        return f"website:{extracted['source_id']}:{extracted['content_hash']}"

    def build_post_dedupe_key(self, extracted: dict) -> str:
        return f"website:{extracted['source_id']}"
