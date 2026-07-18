"""Database tools for the Pydantic AI academic builder."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from typing import Any, Iterable

import psycopg2
import psycopg2.extras

from .academic_schemas import AcademicAgentResult, HomepageRawRow
from .config import PipelineConfig


ACADEMIC_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS academic_institutions (
    id bigserial PRIMARY KEY,
    institution_key varchar(255) NOT NULL UNIQUE,
    name varchar(255) NOT NULL,
    name_en varchar(255) NULL,
    institution_type varchar(48) NOT NULL,
    parent_id bigint NULL REFERENCES academic_institutions(id) ON DELETE SET NULL,
    university_id bigint NULL REFERENCES academic_institutions(id) ON DELETE SET NULL,
    official_url text NULL,
    aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_urls jsonb NOT NULL DEFAULT '[]'::jsonb,
    confidence numeric(4,3) NOT NULL DEFAULT 0.000,
    verification_status varchar(32) NOT NULL DEFAULT 'agent_verified',
    status varchar(32) NOT NULL DEFAULT 'active',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_academic_institutions_type
ON academic_institutions (institution_type);

CREATE INDEX IF NOT EXISTS ix_academic_institutions_parent
ON academic_institutions (parent_id);

CREATE INDEX IF NOT EXISTS ix_academic_institutions_university
ON academic_institutions (university_id);

CREATE TABLE IF NOT EXISTS academic_people (
    id bigserial PRIMARY KEY,
    person_key varchar(255) NOT NULL UNIQUE,
    name_cn varchar(128) NOT NULL,
    name_en varchar(128) NULL,
    normalized_name varchar(160) NOT NULL,
    email text NULL,
    homepage_url text NULL,
    aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
    evidence_urls jsonb NOT NULL DEFAULT '[]'::jsonb,
    confidence numeric(4,3) NOT NULL DEFAULT 0.000,
    verification_status varchar(32) NOT NULL DEFAULT 'agent_verified',
    status varchar(32) NOT NULL DEFAULT 'active',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_academic_people_name
ON academic_people (normalized_name);

CREATE TABLE IF NOT EXISTS academic_affiliations (
    id bigserial PRIMARY KEY,
    person_id bigint NOT NULL REFERENCES academic_people(id) ON DELETE CASCADE,
    institution_id bigint NOT NULL REFERENCES academic_institutions(id) ON DELETE CASCADE,
    role varchar(64) NULL,
    title varchar(128) NULL,
    is_primary boolean NOT NULL DEFAULT false,
    evidence_urls jsonb NOT NULL DEFAULT '[]'::jsonb,
    confidence numeric(4,3) NOT NULL DEFAULT 0.000,
    verification_status varchar(32) NOT NULL DEFAULT 'agent_verified',
    status varchar(32) NOT NULL DEFAULT 'active',
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_verified_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (person_id, institution_id)
);

CREATE INDEX IF NOT EXISTS ix_academic_affiliations_institution
ON academic_affiliations (institution_id);

CREATE TABLE IF NOT EXISTS post_entity_links (
    id bigserial PRIMARY KEY,
    post_id bigint NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    entity_type varchar(48) NOT NULL,
    entity_id bigint NOT NULL,
    relation_type varchar(64) NOT NULL,
    confidence numeric(4,3) NOT NULL DEFAULT 0.000,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (post_id, entity_type, entity_id, relation_type)
);

CREATE TABLE IF NOT EXISTS agent_runs (
    id bigserial PRIMARY KEY,
    source_id varchar(160) NOT NULL,
    content_hash varchar(128) NOT NULL,
    raw_page_id bigint NULL,
    task_type varchar(64) NOT NULL DEFAULT 'academic_builder',
    status varchar(32) NOT NULL,
    reason text NULL,
    model varchar(128) NULL,
    actions jsonb NOT NULL DEFAULT '[]'::jsonb,
    output_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
    usage jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz NULL,
    UNIQUE (source_id, content_hash, task_type)
);

ALTER TABLE agent_runs
ADD COLUMN IF NOT EXISTS usage jsonb NOT NULL DEFAULT '{}'::jsonb;
"""


UPSERT_POST_SQL = """
INSERT INTO posts (
    source_type, post_type, title, category, status,
    author_user_id, summary, content,
    university_name, school_name, major_name,
    source_url, dedupe_key, metadata,
    created_at, updated_at, deleted_at
) VALUES (
    %(source_type)s, %(post_type)s, %(title)s, %(category)s, %(status)s,
    %(author_user_id)s, %(summary)s, %(content)s,
    %(university_name)s, %(school_name)s, %(major_name)s,
    %(source_url)s, %(dedupe_key)s, %(metadata)s,
    %(created_at)s, %(updated_at)s, %(deleted_at)s
)
ON CONFLICT (dedupe_key) DO UPDATE SET
    title = EXCLUDED.title,
    category = EXCLUDED.category,
    summary = EXCLUDED.summary,
    content = EXCLUDED.content,
    university_name = EXCLUDED.university_name,
    school_name = EXCLUDED.school_name,
    major_name = EXCLUDED.major_name,
    source_url = EXCLUDED.source_url,
    metadata = EXCLUDED.metadata,
    updated_at = EXCLUDED.updated_at
RETURNING id
"""


class AcademicRepository:
    def __init__(self, config: PipelineConfig, dry_run: bool = False):
        self.config = config
        self.dry_run = dry_run
        self._conn: "psycopg2.extensions.connection | None" = None
        self._schema_ready = False
        self._fake_id = 100000

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.config.database_url)
            self._conn.set_session(autocommit=True)
            self._schema_ready = False
        self.ensure_schema()
        return self._conn

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()

    def ensure_schema(self) -> None:
        if self.dry_run or self._schema_ready:
            return
        if self._conn is None:
            return
        with self._conn.cursor() as cur:
            cur.execute(ACADEMIC_SCHEMA_SQL)
        self._schema_ready = True

    def load_raw_rows(
        self,
        limit: int = 0,
        source_id: str = "",
        include_processed: bool = False,
        task_type: str = "academic_builder",
    ) -> list[HomepageRawRow]:
        if not self.dry_run:
            _ = self.conn
        clauses = ["status = 'success'", "content_hash IS NOT NULL", "content_hash <> ''"]
        params: list[Any] = []
        if source_id:
            clauses.append("source_id = %s")
            params.append(source_id)
        if not include_processed and not self.dry_run:
            clauses.append(
                """
                NOT EXISTS (
                    SELECT 1 FROM agent_runs ar
                    WHERE ar.source_id = homepage_raw_page.source_id
                      AND ar.content_hash = homepage_raw_page.content_hash
                      AND ar.task_type = %s
                )
                """
            )
            params.append(task_type)
        sql = f"""
            SELECT id, source_id, batch, university, source_type, name,
                   requested_url, final_url, http_status, fetched_at,
                   page_title, markdown, text, content_hash
            FROM homepage_raw_page
            WHERE {' AND '.join(clauses)}
            ORDER BY fetched_at DESC
        """
        if limit:
            sql += " LIMIT %s"
            params.append(limit)
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [HomepageRawRow.from_db_row(dict(row)) for row in cur.fetchall()]

    def save_agent_run(
        self,
        raw: HomepageRawRow,
        result: AcademicAgentResult,
        actions: list[dict[str, Any]],
        model: str,
        usage: dict[str, int] | None = None,
        task_type: str = "academic_builder",
    ) -> None:
        if self.dry_run:
            return
        row = {
            "source_id": raw.source_id,
            "content_hash": raw.content_hash,
            "raw_page_id": raw.id,
            "task_type": task_type,
            "status": result.status,
            "reason": result.reason,
            "model": model,
            "actions": psycopg2.extras.Json(actions),
            "output_summary": psycopg2.extras.Json(result.model_dump()),
            "usage": psycopg2.extras.Json(usage or {}),
        }
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_runs (
                    source_id, content_hash, raw_page_id, task_type, status,
                    reason, model, actions, output_summary, usage, finished_at
                ) VALUES (
                    %(source_id)s, %(content_hash)s, %(raw_page_id)s, %(task_type)s, %(status)s,
                    %(reason)s, %(model)s, %(actions)s, %(output_summary)s, %(usage)s, now()
                )
                ON CONFLICT (source_id, content_hash, task_type) DO UPDATE SET
                    status = EXCLUDED.status,
                    reason = EXCLUDED.reason,
                    model = EXCLUDED.model,
                    actions = EXCLUDED.actions,
                    output_summary = EXCLUDED.output_summary,
                    usage = EXCLUDED.usage,
                    finished_at = now()
                """,
                row,
            )

    def find_institution(
        self,
        name: str,
        institution_type: str = "",
        university_id: int | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        clauses = ["status = 'active'", "name ILIKE %s"]
        params: list[Any] = [f"%{name.strip()}%"]
        if institution_type:
            clauses.append("institution_type = %s")
            params.append(institution_type)
        if university_id:
            clauses.append("(university_id = %s OR id = %s)")
            params.extend([university_id, university_id])
        params.append(max(1, min(limit, 20)))
        sql = f"""
            SELECT id, name, name_en, institution_type, parent_id, university_id,
                   official_url, evidence_urls, confidence, verification_status, metadata
            FROM academic_institutions
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence DESC, updated_at DESC
            LIMIT %s
        """
        if self.dry_run:
            return []
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_normalize_json_row(dict(row)) for row in cur.fetchall()]

    def upsert_institution(
        self,
        name: str,
        institution_type: str,
        name_en: str = "",
        parent_id: int | None = None,
        university_id: int | None = None,
        official_url: str = "",
        aliases: list[str] | None = None,
        evidence_urls: list[str] | None = None,
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence = _only_urls(evidence_urls or [])
        if not evidence:
            return {"skipped": True, "reason": "institution missing evidence URLs"}
        institution_type = _canonical_institution_type(name, name_en, institution_type)
        aliases = _institution_aliases(name, name_en, aliases or [])
        key_name = _canonical_institution_key_name(name, name_en, aliases)
        if institution_type == "university":
            institution_key = f"university:{_normalize_key(key_name)}"
        else:
            if university_id is None and parent_id:
                university_id = self._institution_university_id(parent_id)
            existing = self._find_same_institution_for_merge(
                name=name,
                name_en=name_en,
                aliases=aliases,
                institution_type=institution_type,
                parent_id=parent_id,
                university_id=university_id,
            )
            if existing:
                institution_key = str(existing["institution_key"])
                metadata = {
                    "merged_by_identity": True,
                    "incoming_institution_type": institution_type,
                    "incoming_name": name,
                    **(metadata or {}),
                }
            else:
                institution_key = (
                    f"institution:{university_id or 0}:{parent_id or 0}:"
                    f"{institution_type}:{_normalize_key(key_name)}"
                )
        if self.dry_run:
            return self._fake_row("academic_institution", name=name, institution_type=institution_type)
        row = {
            "institution_key": _truncate(institution_key, 255),
            "name": _truncate(key_name, 255),
            "name_en": _truncate(name_en, 255) or None,
            "institution_type": _truncate(institution_type, 48),
            "parent_id": parent_id,
            "university_id": university_id,
            "official_url": official_url.strip() or None,
            "aliases": psycopg2.extras.Json(aliases),
            "evidence_urls": psycopg2.extras.Json(evidence),
            "confidence": _clamp_confidence(confidence),
            "metadata": psycopg2.extras.Json(metadata or {}),
        }
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO academic_institutions (
                    institution_key, name, name_en, institution_type, parent_id, university_id,
                    official_url, aliases, evidence_urls, confidence, metadata
                ) VALUES (
                    %(institution_key)s, %(name)s, %(name_en)s, %(institution_type)s, %(parent_id)s,
                    %(university_id)s, %(official_url)s, %(aliases)s, %(evidence_urls)s,
                    %(confidence)s, %(metadata)s
                )
                ON CONFLICT (institution_key) DO UPDATE SET
                    name = EXCLUDED.name,
                    name_en = COALESCE(EXCLUDED.name_en, academic_institutions.name_en),
                    parent_id = COALESCE(EXCLUDED.parent_id, academic_institutions.parent_id),
                    university_id = COALESCE(EXCLUDED.university_id, academic_institutions.university_id),
                    official_url = COALESCE(EXCLUDED.official_url, academic_institutions.official_url),
                    aliases = EXCLUDED.aliases,
                    evidence_urls = EXCLUDED.evidence_urls,
                    confidence = GREATEST(academic_institutions.confidence, EXCLUDED.confidence),
                    metadata = academic_institutions.metadata || EXCLUDED.metadata,
                    updated_at = now()
                RETURNING *
                """,
                row,
            )
            saved = _normalize_json_row(dict(cur.fetchone()))
            if saved["institution_type"] == "university" and saved.get("university_id") is None:
                cur.execute(
                    "UPDATE academic_institutions SET university_id = id WHERE id = %s RETURNING *",
                    (saved["id"],),
                )
                saved = _normalize_json_row(dict(cur.fetchone()))
            return saved

    def _find_same_institution_for_merge(
        self,
        name: str,
        name_en: str,
        aliases: list[str],
        institution_type: str,
        parent_id: int | None,
        university_id: int | None,
    ) -> dict[str, Any] | None:
        if self.dry_run or not university_id:
            return None
        incoming_identities = _institution_identity_set(name, name_en, aliases)
        if not incoming_identities:
            return None
        type_family = _institution_type_family(institution_type)
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM academic_institutions
                WHERE status = 'active'
                  AND institution_type = ANY(%s)
                  AND (university_id = %s OR id = %s)
                  AND (%s IS NULL OR parent_id = %s OR id = %s)
                ORDER BY updated_at DESC, id DESC
                """,
                (type_family, university_id, university_id, parent_id, parent_id, parent_id),
            )
            for row in cur.fetchall():
                candidate = _normalize_json_row(dict(row))
                candidate_identities = _institution_identity_set(
                    str(candidate.get("name") or ""),
                    str(candidate.get("name_en") or ""),
                    candidate.get("aliases") or [],
                )
                if incoming_identities & candidate_identities:
                    return candidate
        return None

    def find_person(self, name: str, university_id: int | None = None, limit: int = 10) -> list[dict[str, Any]]:
        clauses = ["status = 'active'", "(normalized_name = %s OR name_cn ILIKE %s OR name_en ILIKE %s)"]
        normalized = _normalize_name(name)
        params: list[Any] = [normalized, f"%{name.strip()}%", f"%{name.strip()}%"]
        if university_id:
            clauses.append(
                """
                EXISTS (
                    SELECT 1 FROM academic_affiliations af
                    JOIN academic_institutions ai ON ai.id = af.institution_id
                    WHERE af.person_id = academic_people.id
                      AND (ai.university_id = %s OR ai.id = %s)
                )
                """
            )
            params.extend([university_id, university_id])
        params.append(max(1, min(limit, 20)))
        sql = f"""
            SELECT id, name_cn, name_en, email, homepage_url, evidence_urls,
                   confidence, verification_status, metadata
            FROM academic_people
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence DESC, updated_at DESC
            LIMIT %s
        """
        if self.dry_run:
            return []
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [_normalize_json_row(dict(row)) for row in cur.fetchall()]

    def upsert_person(
        self,
        name_cn: str,
        university_id: int,
        name_en: str = "",
        email: str = "",
        homepage_url: str = "",
        aliases: list[str] | None = None,
        evidence_urls: list[str] | None = None,
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence = _only_urls(evidence_urls or [])
        if not evidence:
            return {"skipped": True, "reason": "person missing evidence URLs"}
        normalized_name = _normalize_name(name_cn or name_en)
        person_key = f"person:{university_id}:{normalized_name}"
        if self.dry_run:
            return self._fake_row("academic_person", name_cn=name_cn, name_en=name_en)
        row = {
            "person_key": _truncate(person_key, 255),
            "name_cn": _truncate(name_cn, 128) or _truncate(name_en, 128),
            "name_en": _truncate(name_en, 128) or None,
            "normalized_name": _truncate(normalized_name, 160),
            "email": email.strip() or None,
            "homepage_url": homepage_url.strip() or None,
            "aliases": psycopg2.extras.Json(_dedupe_strings(aliases or [])),
            "evidence_urls": psycopg2.extras.Json(evidence),
            "confidence": _clamp_confidence(confidence),
            "metadata": psycopg2.extras.Json(metadata or {}),
        }
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO academic_people (
                    person_key, name_cn, name_en, normalized_name, email, homepage_url,
                    aliases, evidence_urls, confidence, metadata
                ) VALUES (
                    %(person_key)s, %(name_cn)s, %(name_en)s, %(normalized_name)s, %(email)s,
                    %(homepage_url)s, %(aliases)s, %(evidence_urls)s, %(confidence)s, %(metadata)s
                )
                ON CONFLICT (person_key) DO UPDATE SET
                    name_cn = EXCLUDED.name_cn,
                    name_en = COALESCE(EXCLUDED.name_en, academic_people.name_en),
                    email = COALESCE(EXCLUDED.email, academic_people.email),
                    homepage_url = COALESCE(EXCLUDED.homepage_url, academic_people.homepage_url),
                    aliases = EXCLUDED.aliases,
                    evidence_urls = EXCLUDED.evidence_urls,
                    confidence = GREATEST(academic_people.confidence, EXCLUDED.confidence),
                    metadata = academic_people.metadata || EXCLUDED.metadata,
                    updated_at = now()
                RETURNING *
                """,
                row,
            )
            return _normalize_json_row(dict(cur.fetchone()))

    def upsert_affiliation(
        self,
        person_id: int,
        institution_id: int,
        role: str = "",
        title: str = "",
        is_primary: bool = False,
        evidence_urls: list[str] | None = None,
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence = _only_urls(evidence_urls or [])
        if not evidence:
            return {"skipped": True, "reason": "affiliation missing evidence URLs"}
        if self.dry_run:
            return self._fake_row("academic_affiliation", person_id=person_id, institution_id=institution_id)
        row = {
            "person_id": person_id,
            "institution_id": institution_id,
            "role": _truncate(role, 64) or None,
            "title": _truncate(title, 128) or None,
            "is_primary": bool(is_primary),
            "evidence_urls": psycopg2.extras.Json(evidence),
            "confidence": _clamp_confidence(confidence),
            "metadata": psycopg2.extras.Json(metadata or {}),
        }
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO academic_affiliations (
                    person_id, institution_id, role, title, is_primary,
                    evidence_urls, confidence, metadata
                ) VALUES (
                    %(person_id)s, %(institution_id)s, %(role)s, %(title)s, %(is_primary)s,
                    %(evidence_urls)s, %(confidence)s, %(metadata)s
                )
                ON CONFLICT (person_id, institution_id) DO UPDATE SET
                    role = COALESCE(EXCLUDED.role, academic_affiliations.role),
                    title = COALESCE(EXCLUDED.title, academic_affiliations.title),
                    is_primary = academic_affiliations.is_primary OR EXCLUDED.is_primary,
                    evidence_urls = EXCLUDED.evidence_urls,
                    confidence = GREATEST(academic_affiliations.confidence, EXCLUDED.confidence),
                    metadata = academic_affiliations.metadata || EXCLUDED.metadata,
                    last_verified_at = now(),
                    updated_at = now()
                RETURNING *
                """,
                row,
            )
            return _normalize_json_row(dict(cur.fetchone()))

    def create_or_update_post(
        self,
        subject_type: str,
        subject_id: int,
        title: str,
        summary: str,
        content: str,
        university_name: str,
        school_name: str = "",
        major_name: str = "",
        source_url: str = "",
        evidence_urls: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        evidence = _only_urls(evidence_urls or [])
        if not evidence:
            return {"skipped": True, "reason": "post missing evidence URLs"}
        subject_type = _normalize_type(subject_type, "person")
        category = "mentor_recruitment"
        dedupe_key = f"{category}:{subject_type}:{subject_id}"
        now = datetime.now(timezone.utc)
        post_metadata = {
            "source_platform": "homepage_academic_agent",
            "subject_type": subject_type,
            "subject_id": subject_id,
            "evidence": evidence,
            **(metadata or {}),
        }
        if self.dry_run:
            return self._fake_row("post", title=title, dedupe_key=dedupe_key)
        row = {
            "source_type": "personal_website",
            "post_type": "crawled_post",
            "title": _truncate(title, 300),
            "category": category,
            "status": "published",
            "author_user_id": None,
            "summary": summary or None,
            "content": content or summary,
            "university_name": _truncate(university_name, 255) or None,
            "school_name": _truncate(school_name, 255) or None,
            "major_name": _truncate(major_name, 255) or None,
            "source_url": source_url or (evidence[0] if evidence else None),
            "dedupe_key": dedupe_key,
            "metadata": json.dumps(post_metadata, ensure_ascii=False),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(UPSERT_POST_SQL, row)
            return {"id": cur.fetchone()["id"], "dedupe_key": dedupe_key, "title": title}

    def link_post_entity(
        self,
        post_id: int,
        entity_type: str,
        entity_id: int,
        relation_type: str,
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.dry_run:
            return self._fake_row("post_entity_link", post_id=post_id, entity_type=entity_type, entity_id=entity_id)
        row = {
            "post_id": post_id,
            "entity_type": _normalize_type(entity_type, "person"),
            "entity_id": entity_id,
            "relation_type": _truncate(_normalize_type(relation_type, "primary_subject"), 64),
            "confidence": _clamp_confidence(confidence),
            "metadata": psycopg2.extras.Json(metadata or {}),
        }
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                INSERT INTO post_entity_links (
                    post_id, entity_type, entity_id, relation_type, confidence, metadata
                ) VALUES (
                    %(post_id)s, %(entity_type)s, %(entity_id)s, %(relation_type)s,
                    %(confidence)s, %(metadata)s
                )
                ON CONFLICT (post_id, entity_type, entity_id, relation_type) DO UPDATE SET
                    confidence = GREATEST(post_entity_links.confidence, EXCLUDED.confidence),
                    metadata = post_entity_links.metadata || EXCLUDED.metadata
                RETURNING *
                """,
                row,
            )
            return _normalize_json_row(dict(cur.fetchone()))

    def merge_duplicate_institutions(self) -> list[dict[str, Any]]:
        if self.dry_run:
            return []
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT *
                FROM academic_institutions
                WHERE status = 'active'
                  AND institution_type <> 'university'
                ORDER BY university_id, id
                """
            )
            rows = [_normalize_json_row(dict(row)) for row in cur.fetchall()]

        groups: dict[tuple[int, str, str], list[dict[str, Any]]] = {}
        for row in rows:
            key = _institution_duplicate_key(row)
            if key is None:
                continue
            groups.setdefault(key, []).append(row)

        merged: list[dict[str, Any]] = []
        for group_rows in groups.values():
            if len(group_rows) < 2:
                continue
            keep = _choose_institution_to_keep(group_rows)
            for duplicate in group_rows:
                if duplicate["id"] == keep["id"]:
                    continue
                self._merge_institution_rows(keep, duplicate)
                merged.append(
                    {
                        "kept_id": keep["id"],
                        "merged_id": duplicate["id"],
                        "name": duplicate["name"],
                        "institution_type": duplicate["institution_type"],
                    }
                )
        return merged

    def _merge_institution_rows(self, keep: dict[str, Any], duplicate: dict[str, Any]) -> None:
        keep_id = int(keep["id"])
        duplicate_id = int(duplicate["id"])
        keep_aliases = keep.get("aliases") or []
        duplicate_aliases = duplicate.get("aliases") or []
        aliases = _dedupe_strings(
            [
                str(keep.get("name") or ""),
                str(keep.get("name_en") or ""),
                *keep_aliases,
                str(duplicate.get("name") or ""),
                str(duplicate.get("name_en") or ""),
                *duplicate_aliases,
            ]
        )
        evidence_urls = _only_urls((keep.get("evidence_urls") or []) + (duplicate.get("evidence_urls") or []))
        merge_metadata = {
            "merged_duplicate_institution_ids": _dedupe_strings(
                [
                    *(keep.get("metadata") or {}).get("merged_duplicate_institution_ids", []),
                    str(duplicate_id),
                ]
            )
        }
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO academic_affiliations (
                    person_id, institution_id, role, title, is_primary,
                    evidence_urls, confidence, verification_status, status,
                    metadata, last_verified_at
                )
                SELECT person_id, %s, role, title, is_primary,
                       evidence_urls, confidence, verification_status, status,
                       metadata || jsonb_build_object('merged_from_institution_id', %s),
                       last_verified_at
                FROM academic_affiliations
                WHERE institution_id = %s
                ON CONFLICT (person_id, institution_id) DO UPDATE SET
                    role = COALESCE(academic_affiliations.role, EXCLUDED.role),
                    title = COALESCE(academic_affiliations.title, EXCLUDED.title),
                    is_primary = academic_affiliations.is_primary OR EXCLUDED.is_primary,
                    evidence_urls = (
                        SELECT COALESCE(jsonb_agg(DISTINCT value), '[]'::jsonb)
                        FROM jsonb_array_elements_text(
                            academic_affiliations.evidence_urls || EXCLUDED.evidence_urls
                        ) AS value
                    ),
                    confidence = GREATEST(academic_affiliations.confidence, EXCLUDED.confidence),
                    metadata = academic_affiliations.metadata || EXCLUDED.metadata,
                    last_verified_at = GREATEST(academic_affiliations.last_verified_at, EXCLUDED.last_verified_at),
                    updated_at = now()
                """,
                (keep_id, duplicate_id, duplicate_id),
            )
            cur.execute("DELETE FROM academic_affiliations WHERE institution_id = %s", (duplicate_id,))
            cur.execute(
                """
                INSERT INTO post_entity_links (
                    post_id, entity_type, entity_id, relation_type, confidence, metadata
                )
                SELECT post_id, entity_type, %s, relation_type, confidence,
                       metadata || jsonb_build_object('merged_from_institution_id', %s)
                FROM post_entity_links
                WHERE entity_type = 'institution'
                  AND entity_id = %s
                ON CONFLICT (post_id, entity_type, entity_id, relation_type) DO UPDATE SET
                    confidence = GREATEST(post_entity_links.confidence, EXCLUDED.confidence),
                    metadata = post_entity_links.metadata || EXCLUDED.metadata
                """,
                (keep_id, duplicate_id, duplicate_id),
            )
            cur.execute(
                "DELETE FROM post_entity_links WHERE entity_type = 'institution' AND entity_id = %s",
                (duplicate_id,),
            )
            cur.execute(
                """
                UPDATE academic_institutions
                SET
                    name_en = COALESCE(academic_institutions.name_en, %s),
                    aliases = %s,
                    evidence_urls = %s,
                    confidence = GREATEST(academic_institutions.confidence, %s),
                    metadata = academic_institutions.metadata || %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    duplicate.get("name_en") or None,
                    psycopg2.extras.Json(aliases),
                    psycopg2.extras.Json(evidence_urls),
                    duplicate.get("confidence") or 0,
                    psycopg2.extras.Json(merge_metadata),
                    keep_id,
                ),
            )
            cur.execute(
                """
                UPDATE academic_institutions
                SET status = 'merged',
                    metadata = metadata || %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    psycopg2.extras.Json(
                        {
                            "merged_into_institution_id": keep_id,
                            "merge_reason": "same_university_type_and_normalized_name",
                        }
                    ),
                    duplicate_id,
                ),
            )

    def _institution_university_id(self, institution_id: int) -> int | None:
        if self.dry_run:
            return None
        with self.conn.cursor() as cur:
            cur.execute("SELECT university_id FROM academic_institutions WHERE id = %s", (institution_id,))
            row = cur.fetchone()
            return row[0] if row else None

    def _fake_row(self, object_type: str, **extra: Any) -> dict[str, Any]:
        self._fake_id += 1
        return {"id": self._fake_id, "dry_run": True, "object_type": object_type, **extra}


def _only_urls(values: Iterable[str]) -> list[str]:
    return _dedupe_strings([value for value in values if str(value).startswith(("http://", "https://"))])


def _institution_aliases(name: str, name_en: str, aliases: Iterable[str]) -> list[str]:
    values: list[str] = [name, name_en, *list(aliases)]
    for value in list(values):
        values.extend(_split_alias_parts(value))
        values.extend(_parenthetical_parts(value))
        stripped = _strip_parenthetical(value)
        if stripped and stripped != value:
            values.append(stripped)
        acronym = _english_acronym(value)
        if acronym:
            values.append(acronym)
    return _dedupe_strings(values)


def _canonical_institution_key_name(name: str, name_en: str, aliases: Iterable[str]) -> str:
    values = _canonical_name_candidates([name, *list(aliases), name_en])
    for value in values:
        stripped = _strip_parenthetical(value)
        if _has_cjk(stripped):
            return stripped
    for value in values:
        stripped = _strip_parenthetical(value)
        if stripped:
            return stripped
    return name.strip() or name_en.strip() or "unknown"


def _canonical_name_candidates(values: Iterable[str]) -> list[str]:
    candidates: list[str] = []
    for value in values:
        parts = _split_alias_parts(value)
        if len(parts) > 1:
            candidates.extend(parts)
        candidates.append(value)
    return candidates


def _institution_identity_set(name: str, name_en: str, aliases: Iterable[str]) -> set[str]:
    identities: set[str] = set()
    for value in _institution_aliases(name, name_en, aliases):
        for candidate in (value, _strip_parenthetical(value), *_parenthetical_parts(value)):
            key = _normalize_key(candidate)
            if len(key) >= 3:
                identities.add(key)
        acronym = _english_acronym(value)
        if acronym:
            identities.add(_normalize_key(acronym))
    return identities


def _canonical_institution_type(name: str, name_en: str, institution_type: str) -> str:
    normalized = _normalize_type(institution_type, "unknown")
    text = f"{name} {name_en}".strip().lower()
    lab_signal = bool(re.search(r"(实验室|\blab\b|\blaboratory\b)", text))
    group_signal = bool(re.search(r"(课题组|团队|研究组|组(?:\s|$|[（(/-])|\bgroup\b|\bteam\b)", text))
    if normalized == "unknown":
        if re.search(r"(学院|\bschool\b|\bcollege\b)", text):
            return "school"
        if re.search(r"(系|\bdepartment\b)", text):
            return "department"
        if re.search(r"(研究院|\binstitute\b)", text):
            return "institute"
        if re.search(r"(中心|\bcenter\b|\bcentre\b)", text):
            return "center"
        if lab_signal and not group_signal:
            return "lab"
        if group_signal and not lab_signal:
            return "research_group"
        return "unknown"
    if normalized not in {"lab", "research_group"}:
        return normalized
    if group_signal and not lab_signal:
        return "research_group"
    if lab_signal and not group_signal:
        return "lab"
    return normalized


def _institution_type_family(institution_type: str) -> list[str]:
    if institution_type in {"lab", "research_group"}:
        return ["lab", "research_group"]
    return [institution_type]


def _institution_duplicate_key(row: dict[str, Any]) -> tuple[int, str, str] | None:
    university_id = row.get("university_id")
    name = str(row.get("name") or "")
    if not university_id or not name.strip():
        return None
    institution_type = str(row.get("institution_type") or "")
    type_family = "research_unit" if institution_type in {"lab", "research_group"} else institution_type
    canon = _normalize_key(_strip_parenthetical(name))
    if not canon:
        return None
    return int(university_id), type_family, canon


def _choose_institution_to_keep(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(rows, key=lambda row: int(row["id"]))[0]


def _strip_parenthetical(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[（(][^（）()]{1,80}[）)]", "", text)
    return re.sub(r"\s+", " ", text).strip(" -_/，,、")


def _parenthetical_parts(value: str) -> list[str]:
    return [
        part.strip()
        for part in re.findall(r"[（(]([^（）()]{1,80})[）)]", str(value or ""))
        if part.strip()
    ]


def _split_alias_parts(value: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"[/|;；、]+", str(value or ""))
        if part.strip()
    ]


def _english_acronym(value: str) -> str:
    words = re.findall(r"[A-Za-z]+", _strip_parenthetical(value))
    if len(words) < 2:
        return ""
    acronym = "".join(word[0] for word in words).upper()
    return acronym if len(acronym) >= 3 else ""


def _has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", str(value or "")))


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _truncate(value: str, max_length: int) -> str:
    item = str(value or "").strip()
    return item[:max_length]


def _normalize_key(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"[^\w\u4e00-\u9fff]+", "_", value)
    value = value.strip("_")
    if len(value) > 120:
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        value = f"{value[:100]}_{digest}"
    return value or "unknown"


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().lower())


def _normalize_type(value: str, default: str) -> str:
    raw = str(value or "").strip().lower()
    mapping = {
        "大学": "university",
        "高校": "university",
        "学校": "university",
        "univ": "university",
        "university": "university",
        "学院": "school",
        "院": "school",
        "school": "school",
        "college": "school",
        "系": "department",
        "院系": "department",
        "department": "department",
        "研究院": "institute",
        "institute": "institute",
        "实验室": "lab",
        "lab": "lab",
        "laboratory": "lab",
        "课题组": "research_group",
        "团队": "research_group",
        "research group": "research_group",
        "research_group": "research_group",
        "中心": "center",
        "center": "center",
        "centre": "center",
        "老师": "person",
        "教师": "person",
        "人员": "person",
        "person": "person",
        "institution": "institution",
        "机构": "institution",
        "affiliation": "affiliation",
        "从属关系": "affiliation",
        "primary subject": "primary_subject",
        "primary_subject": "primary_subject",
        "主体": "primary_subject",
        "recruitment for": "recruitment_for",
        "recruitment_for": "recruitment_for",
        "招生对象": "recruitment_for",
        "source from": "source_from",
        "source_from": "source_from",
        "来源": "source_from",
        "mentions": "mentions",
        "提及": "mentions",
    }
    if raw in mapping:
        return mapping[raw]
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_")
    return mapping.get(normalized, normalized or default)


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _normalize_json_row(row: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(row.items()):
        if isinstance(value, str) and key in {"metadata", "evidence_urls", "aliases"}:
            try:
                row[key] = json.loads(value)
            except json.JSONDecodeError:
                pass
        elif hasattr(value, "isoformat"):
            row[key] = value.isoformat()
        elif hasattr(value, "__float__") and value.__class__.__module__ == "decimal":
            row[key] = float(value)
    return row
