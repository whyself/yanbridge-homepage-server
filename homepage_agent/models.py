"""Small data models for the standalone homepage agent."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class TeacherProfile:
    action: str = "irrelevant"
    university_name: str = ""
    school_name: str = ""
    lab_name: str = ""
    teacher_name_cn: str = ""
    teacher_name_en: str = ""
    title: str = ""
    email: str = ""
    research_directions: list[str] = field(default_factory=list)
    has_recruitment: bool = False
    recruitment_text: str = ""
    evidence: list[str] = field(default_factory=list)

    @property
    def teacher_name(self) -> str:
        return self.teacher_name_cn or self.teacher_name_en

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PostDraft:
    title: str
    content: str = ""
    summary: str = ""
    university_name: str = ""
    school_name: str = ""
    major_name: str = ""
    source_url: str = ""
    dedupe_key: str = ""
    teacher_name_cn: str = ""
    teacher_name_en: str = ""
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

