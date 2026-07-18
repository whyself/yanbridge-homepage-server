"""Small PydanticAI harness for the teacher-post agent.

The database and CRW implementations live in ``agent_tools.py`` so the same
typed tools can be reused by another harness later.
"""

from __future__ import annotations

from pydantic_ai import Agent

from .agent_tools import (
    AgentToolbox,
    CrwScrapeInput,
    CrwScrapeOutput,
    CrwSearchInput,
    CrwSearchOutput,
    FindPostOutput,
    FindPostQuery,
    UpdatePostInput,
    UpdatePostOutput,
)
from .config import PipelineConfig


TEACHER_POST_AGENT_INSTRUCTIONS = """
You are a narrow Yanbridge teacher-post maintenance agent.

Rules:
1. Use CRW tools only for web search/scrape evidence.
2. Use find_post before update_post unless the user provides a clear dedupe_key.
3. update_post can update an existing post or create a new one.
4. Never ask for or produce SQL.
5. Evidence must be URLs only.
6. Prefer teacher_name_cn as the display/default teacher name; use teacher_name_en only when Chinese name is unavailable.
7. Return a concise summary of what changed and the evidence URLs used.
""".strip()


def build_teacher_post_agent(
    config: PipelineConfig | None = None,
    toolbox: AgentToolbox | None = None,
    model: str | None = None,
) -> Agent[None, str]:
    """Build the single-agent V0 harness with four typed tools."""
    cfg = config or PipelineConfig()
    tools = toolbox or AgentToolbox(cfg)
    selected_model = model or cfg.agent_model
    if not selected_model:
        raise ValueError("Set AGENT_MODEL or pass model=... to build_teacher_post_agent().")

    agent = Agent(
        selected_model,
        instructions=TEACHER_POST_AGENT_INSTRUCTIONS,
        name="yanbridge_teacher_post_agent",
    )

    @agent.tool_plain
    def crw_search(query: str, limit: int = 5) -> CrwSearchOutput:
        """Search the web with CRW for teacher, school, lab, or recruitment evidence."""
        return tools.crw_search(CrwSearchInput(query=query, limit=limit))

    @agent.tool_plain
    def crw_scrape(url: str) -> CrwScrapeOutput:
        """Scrape one URL with CRW and return markdown/text plus metadata."""
        return tools.crw_scrape(CrwScrapeInput(url=url))

    @agent.tool_plain
    def find_post(query: FindPostQuery) -> FindPostOutput:
        """Find existing posts by dedupe key, source URL, teacher, university, school, or keyword."""
        return tools.find_post(query)

    @agent.tool_plain
    def update_post(post: UpdatePostInput) -> UpdatePostOutput:
        """Update an existing post or create one using safe structured fields."""
        return tools.update_post(post)

    return agent


__all__ = ["TEACHER_POST_AGENT_INSTRUCTIONS", "build_teacher_post_agent"]
