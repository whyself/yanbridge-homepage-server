"""Homepage (教师主页) 适配器。

从 homepage_raw_page 表字段映射到统一 Post 结构。
"""

from __future__ import annotations

from ..models import LLMResult, Post, PostCategory, RawRecord, SourceType
from .base import AbstractSourceAdapter




SYSTEM_PROMPT = """你是一个学术信息分析助手。用户会给你一个高校教师/课题组主页的页面信息。

请判断：
1. （重要）如果不包含招生信息，则请过滤掉(irrelevant)；如果正文有明确招生信息（比如招收硕士/博士/本科科研实习等等）则保留
2. 生成一个简洁标题（不超过50字），格式："{学校}{学院}{姓名/课题组}招生"，如"复旦大学计算机学院陈阳老师招收博士生"
3. 从页面内容中提取以下信息（找不到填空字符串）：
   - university: 学校名称
   - school: 学院/系名称
   - major: 专业/研究方向（可以是多个，用逗号分隔，取最核心的1-3个）
4. 判断页面类别 category（四选一）：
   - mentor_recruitment: 教师个人主页/课题组主页（绝大多数情况）
   - student_application: 学生自荐页面
   - project_cooperation: 项目合作/成果展示
   - academic_exchange: 学术交流/会议信息
5. 将页面正文改写为招生帖子格式，输出合法 markdown。要求：
   - 保留原文关键信息（导师姓名、学校、专业方向、联系方式等）
   - 保持原本的语言风格，使得改写（比如修正md格式，过滤无关信息）
   - 不要编造原文中没有的事实信息

严格以 JSON 格式返回，不要输出其他内容：
{"action": "keep" | "irrelevant", "title": "生成的标题", "university": "", "school": "", "major": "", "category":, "summary": "摘要内容", "content": "改写后的招生帖正文(markdown)"}

示例：
- 复旦大学陈阳教授主页有招生信息 → {"action": "keep", "title": "复旦大学计算机学院陈阳老师主页", "university": "复旦大学", "school": "计算机科学技术学院", "major": "计算机网络,分布式系统", "category": "mentor_recruitment", "summary": "陈阳，复旦大学计算机学院教授。主要研究方向为计算机网络体系结构、分布式系统与云计算，课题组长期招收硕士和博士研究生。", "content": "## 复旦大学计算机学院陈阳老师招收研究生\\n\\n陈阳教授，博士生导师，就职于复旦大学计算机科学技术学院。\\n\\n### 研究方向\\n- 计算机网络体系结构\\n- 分布式系统与云计算\\n\\n### 招生要求\\n课题组长期招收硕士和博士研究生，欢迎对计算机网络、分布式系统感兴趣的同学联系。\\n\\n### 联系方式\\n详见主页..."}
- 复旦大学陈阳教授主页没有招生信息 → {"action": "irrelevant", "title": "复旦大学计算机学院陈阳老师主页", "university": "复旦大学", "school": "计算机科学技术学院", "major": "计算机网络,分布式系统", "category": "mentor_recruitment", "summary": "陈阳，复旦大学计算机学院教授。主要研究方向为计算机网络体系结构、分布式系统与云计算，课题组长期招收硕士和博士研究生。", "content": ""}
- 404/空白页 → {"action": "irrelevant", "title": "", "university": "", "school": "", "major": "", "category": "", "summary": "", "content": ""}"""


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

        post = Post(
            source_type=self.source_type,
            post_type="crawled_post",
            title=llm_result.title or extracted["page_title"],
            category=category,
            status="published",
            author_user_id=None,
            summary=llm_result.summary or "",
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
            "name": extracted["name"],
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
