"""Schemas for the academic profile builder."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class HomepageRawRow(BaseModel):
    id: int | None = None
    source_id: str
    batch: str = ""
    university: str = ""
    source_type: Literal["faculty", "lab"] | str = ""
    name: str = ""
    requested_url: str = ""
    final_url: str = ""
    http_status: int | None = None
    fetched_at: str = ""
    page_title: str = ""
    markdown: str = ""
    text: str = ""
    content_hash: str = ""

    @property
    def url(self) -> str:
        return self.final_url or self.requested_url

    @classmethod
    def from_db_row(cls, row: dict[str, Any]) -> "HomepageRawRow":
        data = dict(row)
        for key in (
            "source_id",
            "batch",
            "university",
            "source_type",
            "name",
            "requested_url",
            "final_url",
            "page_title",
            "markdown",
            "text",
            "content_hash",
        ):
            if data.get(key) is None:
                data[key] = ""
        for key in ("fetched_at",):
            value = data.get(key)
            if hasattr(value, "isoformat"):
                data[key] = value.isoformat()
        return cls(**data)


class ExtractedInstitution(BaseModel):
    name: str = ""
    institution_type: Literal[
        "university",
        "school",
        "department",
        "institute",
        "lab",
        "research_group",
        "center",
        "unknown",
    ] = "unknown"
    name_en: str = ""
    parent_name: str = ""
    confidence: float = Field(default=0, ge=0, le=1)


class ExtractedPerson(BaseModel):
    name_cn: str = ""
    name_en: str = ""
    title: str = ""
    email: str = ""
    confidence: float = Field(default=0, ge=0, le=1)


class ExtractedAffiliation(BaseModel):
    person_name: str = ""
    institution_name: str = ""
    role: str = ""
    title: str = ""
    is_primary: bool = False
    confidence: float = Field(default=0, ge=0, le=1)


class ExtractedRecruitment(BaseModel):
    has_recruitment: bool = False
    target_type: Literal["person", "institution", "unknown"] = "unknown"
    target_name: str = ""
    summary: str = ""
    evidence_text: str = ""
    post_title: str = ""
    post_markdown: str = ""
    confidence: float = Field(default=0, ge=0, le=1)


class AcademicExtraction(BaseModel):
    matches_hint: bool = False
    page_type: Literal[
        "faculty_profile",
        "lab_homepage",
        "recruitment_notice",
        "directory",
        "irrelevant",
        "unknown",
    ] = "unknown"
    confidence: float = Field(default=0, ge=0, le=1)
    reason: str = ""
    institutions: list[ExtractedInstitution] = Field(default_factory=list)
    person: ExtractedPerson | None = None
    affiliations: list[ExtractedAffiliation] = Field(default_factory=list)
    recruitment: ExtractedRecruitment = Field(default_factory=ExtractedRecruitment)


class AcademicAgentResult(BaseModel):
    status: Literal["succeeded", "skipped", "failed"] = Field(
        description="succeeded if useful data was written, skipped if deterministic resolver checks reject the page, failed only for execution errors"
    )
    confidence: float = Field(ge=0, le=1)
    summary: str
    reason: str | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    created_post: bool = False
    institution_ids: list[int] = Field(default_factory=list)
    person_ids: list[int] = Field(default_factory=list)
    affiliation_ids: list[int] = Field(default_factory=list)
    post_id: int | None = None


def compact_raw_text(raw: HomepageRawRow, max_chars: int = 8000) -> str:
    text = raw.text or raw.markdown or ""
    text = " ".join(text.split())
    return text[:max_chars]
