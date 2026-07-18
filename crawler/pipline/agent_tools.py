"""Typed, framework-independent tools for the teacher-post agent.

The LLM should call these tools through an agent harness; the tools never
accept SQL and can also be reused by another harness later.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel, Field

from .config import PipelineConfig
from .writer import PostWriter


class CrwSearchInput(BaseModel):
    query: str = Field(..., description="Search query.")
    limit: int = Field(default=5, ge=1, le=20)


class CrwSearchItem(BaseModel):
    title: str = ""
    url: str = ""
    description: str = ""


class CrwSearchOutput(BaseModel):
    results: list[CrwSearchItem] = Field(default_factory=list)


class CrwScrapeInput(BaseModel):
    url: str = Field(..., description="URL to scrape.")


class CrwScrapeOutput(BaseModel):
    url: str = ""
    title: str = ""
    markdown: str = ""
    text: str = ""
    html: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FindPostQuery(BaseModel):
    dedupe_key: str = ""
    source_url: str = ""
    university_name: str = ""
    school_name: str = ""
    teacher_name: str = ""
    keyword: str = ""
    limit: int = Field(default=10, ge=1, le=50)


class PostMatch(BaseModel):
    id: int | None = None
    source_type: str = ""
    post_type: str = ""
    title: str = ""
    category: str = ""
    status: str = ""
    summary: str | None = None
    university_name: str | None = None
    school_name: str | None = None
    major_name: str | None = None
    source_url: str | None = None
    dedupe_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class FindPostOutput(BaseModel):
    matches: list[PostMatch] = Field(default_factory=list)


class UpdatePostInput(BaseModel):
    title: str
    content: str | None = None
    summary: str | None = None
    university_name: str | None = None
    school_name: str | None = None
    major_name: str | None = None
    source_url: str | None = None
    dedupe_key: str | None = None
    category: str = "mentor_recruitment"
    status: str = "published"
    source_type: str = "personal_website"
    post_type: str = "crawled_post"
    teacher_name_cn: str | None = None
    teacher_name_en: str | None = None
    evidence: list[str] = Field(default_factory=list, description="Evidence URLs only.")
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpdatePostOutput(BaseModel):
    post: PostMatch


class AgentToolbox:
    """Portable implementation for CRW and post DB tools."""

    def __init__(self, config: PipelineConfig | None = None):
        self.config = config or PipelineConfig()
        self.writer = PostWriter(self.config)

    def crw_search(self, request: CrwSearchInput) -> CrwSearchOutput:
        payload = {"query": request.query, "limit": request.limit}
        data = self._post_crw("/v1/search", payload)
        raw_items = data.get("data") or data.get("results") or []
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("results") or raw_items.get("data") or []

        items: list[CrwSearchItem] = []
        for item in raw_items[: request.limit]:
            if not isinstance(item, dict):
                continue
            items.append(
                CrwSearchItem(
                    title=str(item.get("title") or ""),
                    url=str(item.get("url") or item.get("link") or ""),
                    description=str(item.get("description") or item.get("snippet") or ""),
                )
            )
        return CrwSearchOutput(results=items)

    def crw_scrape(self, request: CrwScrapeInput) -> CrwScrapeOutput:
        data = self._post_crw("/v1/scrape", {"url": request.url})
        body = data.get("data") if isinstance(data.get("data"), dict) else data
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        return CrwScrapeOutput(
            url=str(body.get("url") or body.get("sourceURL") or request.url),
            title=str(metadata.get("title") or body.get("title") or ""),
            markdown=str(body.get("markdown") or ""),
            text=str(body.get("text") or body.get("content") or ""),
            html=str(body.get("html") or ""),
            metadata=metadata,
        )

    def find_post(self, query: FindPostQuery) -> FindPostOutput:
        rows = self.writer.find_posts(query.model_dump())
        return FindPostOutput(matches=[_row_to_post_match(row) for row in rows])

    def update_post(self, request: UpdatePostInput) -> UpdatePostOutput:
        data = request.model_dump()
        metadata = dict(request.metadata)
        if request.teacher_name_cn:
            metadata["teacher_name_cn"] = request.teacher_name_cn
            metadata.setdefault("teacher_name", request.teacher_name_cn)
        if request.teacher_name_en:
            metadata["teacher_name_en"] = request.teacher_name_en
            metadata.setdefault("teacher_name", request.teacher_name_en)
        if request.evidence:
            metadata["evidence"] = request.evidence
        data["metadata"] = metadata
        row = self.writer.update_post(data)
        return UpdatePostOutput(post=_row_to_post_match(row))

    def close(self) -> None:
        self.writer.close()

    def _post_crw(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.crw_api_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.config.crw_api_key:
            headers["Authorization"] = f"Bearer {self.config.crw_api_key}"

        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.crw_timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"CRW {path} failed: HTTP {exc.code} {detail}") from exc


def _row_to_post_match(row: dict[str, Any]) -> PostMatch:
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {"raw_metadata": metadata}
    return PostMatch(
        id=row.get("id"),
        source_type=str(row.get("source_type") or ""),
        post_type=str(row.get("post_type") or ""),
        title=str(row.get("title") or ""),
        category=str(row.get("category") or ""),
        status=str(row.get("status") or ""),
        summary=row.get("summary"),
        university_name=row.get("university_name"),
        school_name=row.get("school_name"),
        major_name=row.get("major_name"),
        source_url=row.get("source_url"),
        dedupe_key=row.get("dedupe_key"),
        metadata=metadata,
        created_at=_to_text(row.get("created_at")),
        updated_at=_to_text(row.get("updated_at")),
    )


def _to_text(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat() if hasattr(value, "isoformat") else str(value)
