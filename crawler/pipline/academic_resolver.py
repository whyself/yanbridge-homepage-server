"""Deterministic resolver for academic extraction results."""

from __future__ import annotations

import re
from typing import Any

from .academic_schemas import AcademicAgentResult, AcademicExtraction, HomepageRawRow
from .academic_tools import AcademicRepository


def resolve_academic_extraction(
    repo: AcademicRepository,
    raw: HomepageRawRow,
    extraction: AcademicExtraction,
) -> tuple[AcademicAgentResult, list[dict[str, Any]]]:
    actions: list[dict[str, Any]] = [
        {"tool": "extract_academic_page", "result": extraction.model_dump()}
    ]

    if not extraction.matches_hint:
        return _skipped("页面与 hint 不匹配: " + (extraction.reason or "no reason"), extraction, actions)

    evidence_urls = [raw.url] if raw.url else []
    if not evidence_urls:
        return _skipped("缺少 raw URL 证据", extraction, actions)

    university = repo.upsert_institution(
        name=raw.university,
        institution_type="university",
        evidence_urls=evidence_urls,
        confidence=extraction.confidence,
        metadata={"resolver": "academic_resolver", "source_id": raw.source_id},
    )
    actions.append({"tool": "upsert_institution", "args": {"name": raw.university}, "result": university})
    if university.get("skipped"):
        return _skipped("无法创建大学实体", extraction, actions)
    university_id = int(university["id"])

    institutions: dict[str, dict[str, Any]] = {_norm(raw.university): university}
    for item in extraction.institutions:
        if not item.name:
            continue
        if item.institution_type == "university" and _same_name(item.name, raw.university):
            continue
        if item.institution_type == "university":
            continue
        if "大学" in item.name and raw.university not in item.name:
            continue
        institution_name = _clean_child_institution_name(item.name, raw.university)
        saved = repo.upsert_institution(
            name=institution_name,
            institution_type=item.institution_type,
            name_en=item.name_en,
            parent_id=university_id,
            university_id=university_id,
            evidence_urls=evidence_urls,
            aliases=_institution_aliases_for_item(raw, item.name, item.name_en, item.parent_name),
            confidence=item.confidence,
            metadata={
                "resolver": "academic_resolver",
                "source_id": raw.source_id,
                "parent_name_hint": item.parent_name,
                "extracted_name": item.name,
            },
        )
        actions.append(
            {
                "tool": "upsert_institution",
                "args": {"name": institution_name, "institution_type": item.institution_type},
                "result": saved,
            }
        )
        if not saved.get("skipped"):
            institutions[_norm(institution_name)] = saved
            institutions[_norm(item.name)] = saved

    person: dict[str, Any] | None = None
    person_name = ""
    if raw.source_type == "faculty":
        extracted_person = extraction.person
        person_name = (extracted_person.name_cn if extracted_person else "") or raw.name
        if not _same_name(person_name, raw.name):
            return _skipped(
                f"抽取姓名 {person_name!r} 与 hint_name {raw.name!r} 不一致",
                extraction,
                actions,
            )
        person_confidence = extracted_person.confidence if extracted_person else extraction.confidence
        person = repo.upsert_person(
            name_cn=raw.name,
            university_id=university_id,
            name_en=extracted_person.name_en if extracted_person else "",
            email=extracted_person.email if extracted_person else "",
            homepage_url=raw.url,
            evidence_urls=evidence_urls,
            confidence=person_confidence,
            metadata={
                "resolver": "academic_resolver",
                "source_id": raw.source_id,
                "title": extracted_person.title if extracted_person else "",
            },
        )
        actions.append({"tool": "upsert_person", "args": {"name_cn": raw.name}, "result": person})
        if person.get("skipped"):
            return _skipped("无法创建人员实体", extraction, actions)

    affiliation_ids: list[int] = []
    if person is not None:
        has_non_university_affiliation = False
        explicit_affiliations = [
            affiliation
            for affiliation in extraction.affiliations
            if _same_name(affiliation.person_name, raw.name) or not affiliation.person_name
        ]
        for affiliation in explicit_affiliations:
            institution = _find_institution(institutions, affiliation.institution_name)
            if institution is None:
                continue
            saved = repo.upsert_affiliation(
                person_id=int(person["id"]),
                institution_id=int(institution["id"]),
                role=affiliation.role,
                title=affiliation.title or (extraction.person.title if extraction.person else ""),
                is_primary=affiliation.is_primary,
                evidence_urls=evidence_urls,
                confidence=affiliation.confidence,
                metadata={"resolver": "academic_resolver", "source_id": raw.source_id},
            )
            actions.append(
                {
                    "tool": "upsert_affiliation",
                    "args": {
                        "person_id": person["id"],
                        "institution_name": affiliation.institution_name,
                    },
                    "result": saved,
                }
            )
            if not saved.get("skipped"):
                affiliation_ids.append(int(saved["id"]))
                if institution.get("institution_type") != "university":
                    has_non_university_affiliation = True

        if not affiliation_ids:
            fallback = _best_non_university(institutions) or university
            saved = repo.upsert_affiliation(
                person_id=int(person["id"]),
                institution_id=int(fallback["id"]),
                role="teacher",
                title=extraction.person.title if extraction.person else "",
                is_primary=True,
                evidence_urls=evidence_urls,
                confidence=extraction.confidence,
                metadata={
                    "resolver": "academic_resolver",
                    "source_id": raw.source_id,
                    "fallback_affiliation": True,
                },
            )
            actions.append(
                {
                    "tool": "upsert_affiliation",
                    "args": {"person_id": person["id"], "institution_id": fallback["id"]},
                    "result": saved,
                }
            )
            if not saved.get("skipped"):
                affiliation_ids.append(int(saved["id"]))
                if fallback.get("institution_type") != "university":
                    has_non_university_affiliation = True
        elif not has_non_university_affiliation:
            for fallback in _non_university_institutions(institutions):
                saved = repo.upsert_affiliation(
                    person_id=int(person["id"]),
                    institution_id=int(fallback["id"]),
                    role="teacher",
                    title=extraction.person.title if extraction.person else "",
                    is_primary=False,
                    evidence_urls=evidence_urls,
                    confidence=extraction.confidence,
                    metadata={
                        "resolver": "academic_resolver",
                        "source_id": raw.source_id,
                        "fallback_child_affiliation": True,
                    },
                )
                actions.append(
                    {
                        "tool": "upsert_affiliation",
                        "args": {"person_id": person["id"], "institution_id": fallback["id"]},
                        "result": saved,
                    }
                )
                if not saved.get("skipped"):
                    affiliation_ids.append(int(saved["id"]))

    created_post = False
    post_id: int | None = None
    recruitment = extraction.recruitment
    if (
        recruitment.has_recruitment
        and recruitment.evidence_text.strip()
        and recruitment.post_title.strip()
        and recruitment.post_markdown.strip()
        and person is not None
    ):
        post = repo.create_or_update_post(
            subject_type="person",
            subject_id=int(person["id"]),
            title=recruitment.post_title.strip(),
            summary=recruitment.summary,
            content=recruitment.post_markdown.strip(),
            university_name=raw.university,
            school_name=_best_school_name(institutions),
            source_url=raw.url,
            evidence_urls=evidence_urls,
            metadata={
                "resolver": "academic_resolver",
                "source_id": raw.source_id,
                "recruitment_evidence_text": recruitment.evidence_text,
                "agent_generated_post": True,
            },
        )
        actions.append({"tool": "create_or_update_post", "args": {"subject_id": person["id"]}, "result": post})
        if not post.get("skipped"):
            created_post = True
            post_id = int(post["id"])
            link = repo.link_post_entity(
                post_id=post_id,
                entity_type="person",
                entity_id=int(person["id"]),
                relation_type="primary_subject",
                confidence=recruitment.confidence,
                metadata={"resolver": "academic_resolver", "source_id": raw.source_id},
            )
            actions.append({"tool": "link_post_entity", "result": link})

    result = AcademicAgentResult(
        status="succeeded",
        confidence=extraction.confidence,
        summary=_summary(raw, extraction, created_post),
        evidence_urls=evidence_urls,
        created_post=created_post,
        institution_ids=[
            int(item["id"]) for item in institutions.values() if isinstance(item.get("id"), int)
        ],
        person_ids=[int(person["id"])] if person is not None else [],
        affiliation_ids=affiliation_ids,
        post_id=post_id,
    )
    return result, actions


def _skipped(
    reason: str,
    extraction: AcademicExtraction,
    actions: list[dict[str, Any]],
) -> tuple[AcademicAgentResult, list[dict[str, Any]]]:
    return (
        AcademicAgentResult(
            status="skipped",
            confidence=extraction.confidence,
            summary="跳过: " + reason,
            reason=reason,
        ),
        actions,
    )


def _summary(raw: HomepageRawRow, extraction: AcademicExtraction, created_post: bool) -> str:
    institution_names = [item.name for item in extraction.institutions if item.name][:4]
    post_part = "已生成招生 Post" if created_post else "未生成招生 Post"
    return (
        f"{raw.source_id} 抽取成功：page_type={extraction.page_type}，"
        f"机构={', '.join(institution_names) or raw.university}，{post_part}。"
    )


def _best_non_university(institutions: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    for item in institutions.values():
        if item.get("institution_type") in {"school", "department", "institute", "lab", "research_group", "center"}:
            return item
    return None


def _non_university_institutions(institutions: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    result: list[dict[str, Any]] = []
    for item in institutions.values():
        item_id = item.get("id")
        if not isinstance(item_id, int) or item_id in seen:
            continue
        if item.get("institution_type") not in {"school", "department", "institute", "lab", "research_group", "center"}:
            continue
        seen.add(item_id)
        result.append(item)
    return result


def _best_school_name(institutions: dict[str, dict[str, Any]]) -> str:
    for item in institutions.values():
        if item.get("institution_type") in {"school", "department", "institute"}:
            return str(item.get("name") or "")
    return ""


def _find_institution(institutions: dict[str, dict[str, Any]], name: str) -> dict[str, Any] | None:
    normalized = _norm(name)
    if normalized in institutions:
        return institutions[normalized]
    for key, value in institutions.items():
        if normalized and (normalized in key or key in normalized):
            return value
    return None


def _same_name(left: str, right: str) -> bool:
    left_norm = _norm(left)
    right_norm = _norm(right)
    return bool(left_norm and right_norm and (left_norm == right_norm or left_norm in right_norm or right_norm in left_norm))


def _clean_child_institution_name(name: str, university_name: str) -> str:
    value = str(name or "").strip()
    university = str(university_name or "").strip()
    if university and value.startswith(university) and value != university:
        value = value[len(university):].strip(" -_/，,、")
    return value or str(name or "").strip()


def _institution_aliases_for_item(
    raw: HomepageRawRow,
    item_name: str,
    item_name_en: str,
    _parent_name: str,
) -> list[str]:
    aliases = [item_name, item_name_en]
    raw_alias = _clean_child_institution_name(raw.name, raw.university)
    if raw.source_type == "lab" and _same_name_or_token_overlap(item_name, item_name_en, raw_alias):
        aliases.extend([raw_alias, raw.name])
    return _dedupe_strings(aliases)


def _same_name_or_token_overlap(item_name: str, item_name_en: str, raw_alias: str) -> bool:
    if _same_name(item_name, raw_alias) or _same_name(item_name_en, raw_alias):
        return True
    raw_parts = [part.strip() for part in re.split(r"[/|;；、]+", raw_alias) if part.strip()]
    for part in raw_parts:
        if _same_name(item_name, part) or _same_name(item_name_en, part):
            return True
    return False


def _dedupe_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value.strip() for value in values if value and value.strip()))


def _norm(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())
