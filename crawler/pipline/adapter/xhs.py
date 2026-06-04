"""XHS (小红书) 适配器。

从 xhs_notes 表字段映射到统一 Post 结构。
"""

from __future__ import annotations

from ..models import LLMResult, Post, PostCategory, RawRecord, SourceType
from .base import AbstractSourceAdapter

# 复用 llm_process.py 的 SYSTEM_PROMPT，新增 category 分类
SYSTEM_PROMPT = """你是一个招生信息分析助手。用户会给你一篇小红书帖子的标题和正文。

请判断：
1. 该帖子是否是真实的招生/课题组/导师招募信息？如果是广告、带货、推销、无关内容，标记为 irrelevant。
2. 标题是否包含学校名、课题组名、老师姓名中至少一个？
   - 如果包含 → 保持原标题不变
   - 如果不包含 → 从正文中提取关键信息，生成一个简洁标题（不超过50字）
   - 如果原来无标题 → 从正文中提取关键信息，生成一个简洁标题（不超过50字）
3. 从标题和正文中提取以下信息（找不到填空字符串）：
   - university: 学校名称，如"南昌大学"
   - school: 学院名称，如"食品学院"
   - major: 专业/方向名称，如"食品科学与工程"
4. 判断帖子类别 category（四选一）：
   - mentor_recruitment: 导师/课题组招生、招聘博士后/科研助理
   - student_application: 学生自荐/求导师/求课题组
   - project_cooperation: 项目合作/课题合作
   - academic_exchange: 学术交流/会议/讲座
5. 将帖子正文改写为招生帖子格式，输出合法 markdown。要求：
   - 保留原文关键信息（导师姓名、学校、专业方向、联系方式等）
   - 保持原本的语言风格，使得改写（比如修正md格式，过滤无关信息）
   - 不要编造原文中没有的事实信息

严格以 JSON 格式返回，不要输出其他内容：
{"action": "keep" | "rewrite" | "irrelevant", "title": "原标题或新标题", "university": "", "school": "", "major": "", "category":, "content": "改写后的招生帖正文(markdown)"}

示例：
- 标题"南昌大学食品学院徐振江老师课题组招生" → {"action": "keep", "title": "南昌大学食品学院徐振江老师课题组招生", "university": "南昌大学", "school": "食品学院", "major": "食品科学与工程", "category": "mentor_recruitment", "content": "## 南昌大学食品学院徐振江老师课题组招生\\n\\n徐振江老师课题组现面向全国招收硕士、博士研究生。研究方向为食品科学与工程...\\n\\n### 申请要求\\n- 食品科学相关专业背景\\n- ..."}
- 标题"研究生必看"但正文提到北大张老师招生 → {"action": "rewrite", "title": "北京大学张老师课题组招收研究生", "university": "北京大学", "school": "", "major": "", "category": "mentor_recruitment", "content": "## 北京大学张老师课题组招收研究生\\n\\n张老师课题组...\\n\\n### 研究方向\\n- ..."}
- 标题"研究生论文辅导" → {"action": "irrelevant", "title": "", "university": "", "school": "", "major": "", "category": "", "content": ""}"""


class XHSAdapter(AbstractSourceAdapter):
    source_type = SourceType.XIAOHONGSHU

    # ------------------------------------------------------------------
    # extract
    # ------------------------------------------------------------------

    def extract(self, raw: RawRecord) -> dict:
        d = raw.raw_data
        return {
            "note_id": d.get("note_id", ""),
            "note_url": d.get("note_url", ""),
            "note_type": d.get("note_type", ""),
            "user_id": d.get("user_id", ""),
            "title": d.get("title", "") or "",
            "description": d.get("description", "") or "",
            "images": d.get("images") or [],
            # 社交元数据（打包到 metadata）这里把xhs额外的字段全部放到这里来
            "nickname": d.get("nickname", ""),
            "avatar": d.get("avatar", ""),
            "home_url": d.get("home_url", ""),
            "liked_count": d.get("liked_count", ""),
            "collected_count": d.get("collected_count", ""),
            "comment_count": d.get("comment_count", ""),
            "share_count": d.get("share_count", ""),
            "tags": d.get("tags") or [],
            "upload_time": _to_str(d.get("upload_time")),
            "ip_location": d.get("ip_location", ""),
            "video_cover": d.get("video_cover"),
            "video_addr": d.get("video_addr"),
            "raw_json": d.get("raw_json", {}),
        }

    # ------------------------------------------------------------------
    # LLM prompt
    # ------------------------------------------------------------------

    def build_llm_prompt(self, extracted: dict) -> tuple[str, str]:
        title = extracted["title"]
        content = extracted["description"][:2000]
        user_msg = f"标题：{title}\n\n正文：{content}"
        return SYSTEM_PROMPT, user_msg

    # ------------------------------------------------------------------
    # OCR
    # ------------------------------------------------------------------

    def needs_ocr(self, extracted: dict) -> bool:
        #WARNING:
        return (
            len(extracted.get("images") or []) > 0
        )


    def to_post(
        self, raw: RawRecord, extracted: dict, llm_result: LLMResult,
        rewritten_content: str | None = None,
    ) -> Post:
        note_id = extracted["note_id"]
        category = llm_result.category or PostCategory.MENTOR_RECRUITMENT

        post = Post(
            source_type=self.source_type,
            post_type="crawled_post",
            title=llm_result.title or extracted["title"],
            category=category,
            status="published",
            author_user_id=None,  # 爬取帖子无平台用户ID, XHS user_id 存于 metadata
            summary=llm_result.summary or extracted["description"],
            university_name=llm_result.university_name or None,
            school_name=llm_result.school_name or None,
            major_name=llm_result.major_name or None,
            source_url=extracted["note_url"],
            dedupe_key=self.build_dedupe_key(extracted),
            created_at=extracted["upload_time"],
            updated_at=extracted["upload_time"],
            deleted_at=None,
        )

        # content: frontmatter + LLM 改写后的招生帖正文 (或原文降级)
        body = llm_result.content or rewritten_content or (extracted["description"] or "")
        post.content = self.build_frontmatter(post) + body

        # metadata: 社交元数据 + 图片 + 原始 JSON
        post.metadata = {
            "nickname": extracted["nickname"],
            "avatar": extracted["avatar"],
            "home_url": extracted["home_url"],
            "liked_count": extracted["liked_count"],
            "collected_count": extracted["collected_count"],
            "comment_count": extracted["comment_count"],
            "share_count": extracted["share_count"],
            "tags": extracted["tags"],
            "upload_time": extracted["upload_time"],
            "ip_location": extracted["ip_location"],
            "video_cover": extracted["video_cover"],
            "video_addr": extracted["video_addr"],
            "note_type": extracted["note_type"],
            "images": extracted["images"],
            "raw_json": extracted["raw_json"],
        }

        # 如果是 rewrite，保留原标题
        if llm_result.action == "rewrite":
            post.metadata["original_title"] = extracted["title"]

        return post

    # ------------------------------------------------------------------
    # dedupe
    # ------------------------------------------------------------------

    def build_dedupe_key(self, extracted: dict) -> str:
        return f"xhs:note:{extracted['note_id']}"


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------

def _to_str(val) -> str:
    """将 datetime / 任意类型转为字符串。"""
    if val is None:
        return ""
    if hasattr(val, "isoformat"):
        return val.isoformat()
    return str(val)
