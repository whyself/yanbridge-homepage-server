"""Single-call Pydantic AI extractor for homepage raw pages.

The model extracts structured data only. It cannot search the web or write to
the database; deterministic resolver code decides what is safe to persist.
"""

from __future__ import annotations

from pydantic_ai import Agent

from .academic_schemas import AcademicExtraction, HomepageRawRow, compact_raw_text
from .config import PipelineConfig


ACADEMIC_EXTRACTOR_PROMPT = """
你是研途星桥的高校主页结构化信息抽取器。

你只根据输入的 homepage_raw_page 内容抽取信息，不搜索互联网，不补全未出现的信息。
如果页面内容和 hint 不匹配，必须设置 matches_hint=false。

抽取规则：
1. source_type=faculty 时，页面必须明确属于 hint_name 这个老师；如果正文主要是另一个人，matches_hint=false。
2. source_type=lab 时，页面必须明确属于 hint_name 这个实验室/课题组/团队。
3. institutions 只填写页面主体当前所属的学校、学院、系、研究院、实验室、课题组、中心。
4. 如果页面匹配 hint，可以把 hint_university 作为 university institution。
5. affiliation 只填写明确出现的人-机构关系；没有明确机构时可以不填。
6. recruitment.has_recruitment 只有在正文明确出现招生、招收硕士/博士、招实习、Join us、Openings 等当前招生意图时才为 true。
7. 招生信息必须给 evidence_text，直接摘录或精简为页面中的证据短句。
8. 如果 recruitment.has_recruitment=true，必须同时输出 post_title 和 post_markdown。
9. post_markdown 是面向学生展示的完整 Markdown 招生帖，不是抽取报告；应该根据页面信息组织内容，可包含“导师简介”“课题组/机构介绍”“研究方向”“招生信息”“申请方式”“信息来源”等章节。
10. post_markdown 只能使用页面正文、hint 和 URL 中能支持的信息；没有出现的信息不要写，不要为了凑章节编造内容。
11. post_markdown 必须包含明确招生信息和来源 URL；evidence_text 保留页面中的招生证据短句。
12. 不要把“研究生教学/招生信息”导航栏当作老师本人招生信息。
13. 不要编造邮箱、职称、学院、实验室、招生内容。
14. 不要把教育经历、过往工作经历、访问经历里的其他大学抽为当前 institution。
15. confidence 反映当前页面对结论的支持强度，信息不足就降低 confidence。
""".strip()


def build_academic_extractor(config: PipelineConfig) -> Agent[None, AcademicExtraction]:
    return Agent(
        _model_name(config),
        output_type=AcademicExtraction,
        instructions=ACADEMIC_EXTRACTOR_PROMPT,
        retries=1,
    )


async def extract_academic_page(
    agent: Agent[None, AcademicExtraction],
    raw: HomepageRawRow,
    max_text_chars: int = 8000,
) -> tuple[AcademicExtraction, dict[str, int]]:
    text = compact_raw_text(raw, max_text_chars)
    prompt = (
        "请抽取以下 homepage_raw_page 的结构化信息。\n\n"
        f"source_id: {raw.source_id}\n"
        f"batch: {raw.batch}\n"
        f"source_type: {raw.source_type}\n"
        f"hint_university: {raw.university}\n"
        f"hint_name: {raw.name}\n"
        f"requested_url: {raw.requested_url}\n"
        f"final_url: {raw.final_url}\n"
        f"page_title: {raw.page_title}\n\n"
        f"正文节选:\n{text}"
    )
    run = await agent.run(prompt)
    return run.output, _usage_dict(run.usage)


def _model_name(config: PipelineConfig) -> str:
    model = config.agent_model or config.deepseek_model or "deepseek-chat"
    if ":" in model:
        return model
    if model.startswith("deepseek-"):
        return f"deepseek:{model}"
    return model


def _usage_dict(usage: object) -> dict[str, int]:
    return {
        "requests": int(getattr(usage, "requests", 0) or 0),
        "tool_calls": int(getattr(usage, "tool_calls", 0) or 0),
        "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
        "cache_write_tokens": int(getattr(usage, "cache_write_tokens", 0) or 0),
        "cache_read_tokens": int(getattr(usage, "cache_read_tokens", 0) or 0),
    }
