"""Post → PostgreSQL posts 表写入。

使用 psycopg2 直接 INSERT ... ON CONFLICT DO UPDATE。
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Iterable

import psycopg2
import psycopg2.extras

from .config import PipelineConfig
from .models import LLMResult, Post


UPSERT_SQL = """
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
"""


DISCARDED_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS discarded_post (
        id bigserial PRIMARY KEY,
        dedupe_key varchar(255) NOT NULL UNIQUE,
        source_type varchar(32) NOT NULL,
        title varchar(500) NULL,
        source_url text NULL,
        reason varchar(64) NOT NULL DEFAULT 'irrelevant',
        metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT now(),
        updated_at timestamptz NOT NULL DEFAULT now()
    )
"""


TEACHER_PROFILES_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS teacher_profiles (
      id bigserial PRIMARY KEY,

      source_id varchar(160) NOT NULL UNIQUE,
      source_batch varchar(64),
      source_type varchar(32),
      action varchar(32) NOT NULL DEFAULT 'irrelevant',

      university_name varchar(128) NOT NULL,
      school_name varchar(160),
      lab_name varchar(160),

      teacher_name_cn varchar(128),
      teacher_name_en varchar(128),
      teacher_name varchar(128) NOT NULL,

      title text,
      email text,
      research_directions jsonb NOT NULL DEFAULT '[]'::jsonb,
      has_recruitment boolean NOT NULL DEFAULT false,
      recruitment_text text,
      evidence jsonb NOT NULL DEFAULT '[]'::jsonb,

      homepage_url text,
      requested_url text,
      post_dedupe_key varchar(255),
      status varchar(32) NOT NULL DEFAULT 'active',
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      last_seen_at timestamptz NOT NULL DEFAULT now(),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
"""


TEACHER_PROFILES_INDEX_SQL = [
    """
    CREATE INDEX IF NOT EXISTS ix_teacher_profiles_university_school
      ON teacher_profiles (university_name, school_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_teacher_profiles_lab
      ON teacher_profiles (lab_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_teacher_profiles_teacher_name
      ON teacher_profiles (teacher_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_teacher_profiles_has_recruitment
      ON teacher_profiles (has_recruitment)
    """,
]


UPSERT_TEACHER_PROFILE_SQL = """
    INSERT INTO teacher_profiles (
        source_id, source_batch, source_type, action,
        university_name, school_name, lab_name,
        teacher_name_cn, teacher_name_en, teacher_name,
        title, email, research_directions, has_recruitment,
        recruitment_text, evidence,
        homepage_url, requested_url, post_dedupe_key,
        status, metadata, last_seen_at, created_at, updated_at
    ) VALUES (
        %(source_id)s, %(source_batch)s, %(source_type)s, %(action)s,
        %(university_name)s, %(school_name)s, %(lab_name)s,
        %(teacher_name_cn)s, %(teacher_name_en)s, %(teacher_name)s,
        %(title)s, %(email)s, %(research_directions)s, %(has_recruitment)s,
        %(recruitment_text)s, %(evidence)s,
        %(homepage_url)s, %(requested_url)s, %(post_dedupe_key)s,
        %(status)s, %(metadata)s, NOW(), NOW(), NOW()
    )
    ON CONFLICT (source_id) DO UPDATE SET
        source_batch = EXCLUDED.source_batch,
        source_type = EXCLUDED.source_type,
        action = EXCLUDED.action,
        university_name = EXCLUDED.university_name,
        school_name = EXCLUDED.school_name,
        lab_name = EXCLUDED.lab_name,
        teacher_name_cn = EXCLUDED.teacher_name_cn,
        teacher_name_en = EXCLUDED.teacher_name_en,
        teacher_name = EXCLUDED.teacher_name,
        title = EXCLUDED.title,
        email = EXCLUDED.email,
        research_directions = EXCLUDED.research_directions,
        has_recruitment = EXCLUDED.has_recruitment,
        recruitment_text = EXCLUDED.recruitment_text,
        evidence = EXCLUDED.evidence,
        homepage_url = EXCLUDED.homepage_url,
        requested_url = EXCLUDED.requested_url,
        post_dedupe_key = EXCLUDED.post_dedupe_key,
        status = EXCLUDED.status,
        metadata = EXCLUDED.metadata,
        last_seen_at = NOW(),
        updated_at = NOW()
"""


SCHOOL_FACULTY_SOURCES_SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS school_faculty_sources (
      id bigserial PRIMARY KEY,

      source_id varchar(160) NOT NULL UNIQUE,
      source_batch varchar(64) NOT NULL,
      source_type varchar(32) NOT NULL DEFAULT 'faculty',

      university_code varchar(32) NOT NULL,
      university_name varchar(128) NOT NULL,

      unit_name varchar(160),
      unit_type varchar(32) NOT NULL DEFAULT 'department',

      faculty_name varchar(128) NOT NULL,
      faculty_key varchar(255) NOT NULL,

      url text NOT NULL,
      requested_url text,
      url_type varchar(32) NOT NULL DEFAULT 'unknown',
      is_primary boolean NOT NULL DEFAULT false,

      status varchar(32) NOT NULL DEFAULT 'active',
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      content_hash varchar(128),
      http_status integer,
      last_seen_at timestamptz NOT NULL DEFAULT now(),
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    )
"""


SCHOOL_FACULTY_INDEX_SQL = [
    """
    CREATE INDEX IF NOT EXISTS ix_school_faculty_sources_university
      ON school_faculty_sources (university_code, university_name)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_school_faculty_sources_faculty
      ON school_faculty_sources (university_code, faculty_key)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_school_faculty_sources_status
      ON school_faculty_sources (status)
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_school_faculty_sources_faculty_url
      ON school_faculty_sources (faculty_key, url)
    """,
]


UPDATE_SCHOOL_FACULTY_SOURCE_SQL = """
    UPDATE school_faculty_sources
    SET source_batch = %(source_batch)s,
        source_type = %(source_type)s,
        university_code = %(university_code)s,
        university_name = %(university_name)s,
        unit_name = %(unit_name)s,
        unit_type = %(unit_type)s,
        faculty_name = %(faculty_name)s,
        requested_url = %(requested_url)s,
        url_type = %(url_type)s,
        is_primary = school_faculty_sources.is_primary OR %(is_primary)s,
        status = %(status)s,
        metadata = %(metadata)s,
        content_hash = %(content_hash)s,
        http_status = %(http_status)s,
        last_seen_at = NOW(),
        updated_at = NOW()
    WHERE source_id = %(source_id)s
       OR (faculty_key = %(faculty_key)s AND url = %(url)s)
"""


INSERT_SCHOOL_FACULTY_SOURCE_SQL = """
    INSERT INTO school_faculty_sources (
        source_id, source_batch, source_type,
        university_code, university_name,
        unit_name, unit_type,
        faculty_name, faculty_key,
        url, requested_url, url_type, is_primary,
        status, metadata, content_hash, http_status,
        last_seen_at, created_at, updated_at
    ) VALUES (
        %(source_id)s, %(source_batch)s, %(source_type)s,
        %(university_code)s, %(university_name)s,
        %(unit_name)s, %(unit_type)s,
        %(faculty_name)s, %(faculty_key)s,
        %(url)s, %(requested_url)s, %(url_type)s, %(is_primary)s,
        %(status)s, %(metadata)s, %(content_hash)s, %(http_status)s,
        NOW(), NOW(), NOW()
    )
"""


UPSERT_DISCARDED_SQL = """
    INSERT INTO discarded_post (
        dedupe_key, source_type, title, source_url, reason, metadata, created_at, updated_at
    ) VALUES (
        %(dedupe_key)s, %(source_type)s, %(title)s, %(source_url)s, %(reason)s, %(metadata)s, NOW(), NOW()
    )
    ON CONFLICT (dedupe_key) DO UPDATE SET
        source_type = EXCLUDED.source_type,
        title = EXCLUDED.title,
        source_url = EXCLUDED.source_url,
        reason = EXCLUDED.reason,
        metadata = EXCLUDED.metadata,
        updated_at = NOW()
"""

MARK_HOMEPAGE_RAW_PROCESSED_SQL = """
    UPDATE homepage_raw_page
    SET pipeline_pending = false,
        updated_at = NOW()
    WHERE source_id = %s
      AND content_hash = %s
"""


class PostWriter:
    """写入 posts 表，支持 dedupe_key 去重的 UPSERT。"""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._conn: "psycopg2.extensions.connection | None" = None
        self._schema_ready = False

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.config.database_url)
            self._conn.set_session(autocommit=True)
            self._schema_ready = False
        self._ensure_schema()
        return self._conn

    def _ensure_schema(self) -> None:
        if self._schema_ready or self._conn is None:
            return
        with self._conn.cursor() as cur:
            cur.execute(DISCARDED_SCHEMA_SQL)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS ix_discarded_post_source_type "
                "ON discarded_post (source_type)"
            )
            cur.execute(SCHOOL_FACULTY_SOURCES_SCHEMA_SQL)
            for sql in SCHOOL_FACULTY_INDEX_SQL:
                cur.execute(sql)
            cur.execute("CREATE INDEX IF NOT EXISTS ix_posts_content_hash ON posts ((metadata->>'content_hash'))")
            cur.execute("CREATE INDEX IF NOT EXISTS ix_discarded_post_content_hash ON discarded_post ((metadata->>'content_hash'))")
        self._schema_ready = True

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def upsert(self, post: Post) -> None:
        """插入或更新一条 Post 记录。"""
        row = post.to_db_row()
        # psycopg2 需要 JSON 字符串转为适配类型
        meta_str = row["metadata"]
        row["metadata"] = meta_str if isinstance(meta_str, str) else json.dumps(meta_str)
        with self.conn.cursor() as cur:
            cur.execute(UPSERT_SQL, row)

    def upsert_many(self, posts: list[Post]) -> None:
        """批量 upsert。"""
        rows = []
        for post in posts:
            row = post.to_db_row()
            meta_str = row["metadata"]
            row["metadata"] = meta_str if isinstance(meta_str, str) else json.dumps(meta_str)
            rows.append(row)
        with self.conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, UPSERT_SQL, rows)

    def find_posts(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        """Find posts for agent tools without exposing SQL to the model."""
        clauses: list[str] = ["deleted_at IS NULL"]
        params: list[Any] = []

        dedupe_key = str(query.get("dedupe_key") or "").strip()
        if dedupe_key:
            clauses.append("dedupe_key = %s")
            params.append(dedupe_key)

        source_url = str(query.get("source_url") or "").strip()
        if source_url:
            clauses.append("source_url = %s")
            params.append(source_url)

        university_name = str(query.get("university_name") or "").strip()
        if university_name:
            clauses.append("university_name ILIKE %s")
            params.append(f"%{university_name}%")

        school_name = str(query.get("school_name") or "").strip()
        if school_name:
            clauses.append("school_name ILIKE %s")
            params.append(f"%{school_name}%")

        teacher_name = str(query.get("teacher_name") or "").strip()
        if teacher_name:
            clauses.append("(title ILIKE %s OR summary ILIKE %s OR metadata->>'teacher_name' ILIKE %s)")
            like = f"%{teacher_name}%"
            params.extend([like, like, like])

        keyword = str(query.get("keyword") or "").strip()
        if keyword:
            clauses.append("(title ILIKE %s OR summary ILIKE %s OR content ILIKE %s)")
            like = f"%{keyword}%"
            params.extend([like, like, like])

        limit = int(query.get("limit") or 10)
        limit = max(1, min(limit, 50))
        params.append(limit)

        sql = f"""
            SELECT id, source_type, post_type, title, category, status,
                   summary, university_name, school_name, major_name,
                   source_url, dedupe_key, metadata, created_at, updated_at
            FROM posts
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
            LIMIT %s
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(row) for row in cur.fetchall()]

    def update_post(self, data: dict[str, Any]) -> dict[str, Any]:
        """Update or create a post for agent tools using the normal posts upsert."""
        now = datetime.now(timezone.utc).isoformat()
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {"agent_metadata": metadata}
        metadata.setdefault("source_platform", "agent")

        dedupe_key = str(data.get("dedupe_key") or "").strip()
        source_url = str(data.get("source_url") or "").strip()
        if not dedupe_key:
            seed = source_url or "|".join(
                str(data.get(key) or "")
                for key in ("university_name", "school_name", "title")
            )
            digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
            dedupe_key = f"agent:post:{digest}"

        post = Post(
            source_type=data.get("source_type") or "personal_website",
            post_type=data.get("post_type") or "crawled_post",
            title=str(data.get("title") or "").strip(),
            category=data.get("category") or "mentor_recruitment",
            status=data.get("status") or "published",
            author_user_id=data.get("author_user_id"),
            summary=data.get("summary"),
            content=data.get("content"),
            university_name=data.get("university_name"),
            school_name=data.get("school_name"),
            major_name=data.get("major_name"),
            source_url=source_url or None,
            dedupe_key=dedupe_key,
            metadata=metadata,
            created_at=data.get("created_at") or now,
            updated_at=data.get("updated_at") or now,
            deleted_at=data.get("deleted_at"),
        )
        self.upsert(post)
        matches = self.find_posts({"dedupe_key": dedupe_key, "limit": 1})
        return matches[0] if matches else {"dedupe_key": dedupe_key, "updated_at": now}

    def upsert_school_faculty_source(
        self,
        extracted: dict,
        llm_result: LLMResult,
        post: Post | None = None,
        raw_version_key: str | None = None,
    ) -> None:
        """Insert/update one homepage faculty source observation."""
        row = self._build_school_faculty_source_row(extracted, llm_result, post, raw_version_key)
        if row is None:
            return
        with self.conn.cursor() as cur:
            cur.execute(UPDATE_SCHOOL_FACULTY_SOURCE_SQL, row)
            if cur.rowcount == 0:
                cur.execute(INSERT_SCHOOL_FACULTY_SOURCE_SQL, row)

    # ------------------------------------------------------------------
    # Resume: 查询已处理的 dedupe_key
    # ------------------------------------------------------------------

    def get_processed_keys(self, prefix: str = "") -> set[str]:
        """从 posts 和 discarded_post 获取已有 dedupe_key，用于 resume。

        prefix: 可选过滤，如 "xhs:note:" 或 "website:"
        """
        with self.conn.cursor() as cur:
            if prefix:
                cur.execute(
                    """
                    SELECT dedupe_key FROM posts WHERE dedupe_key LIKE %s
                    UNION
                    SELECT metadata->>'raw_version_key'
                    FROM posts
                    WHERE metadata->>'raw_version_key' LIKE %s
                    UNION
                    SELECT dedupe_key FROM discarded_post WHERE dedupe_key LIKE %s
                    """,
                    (prefix + "%", prefix + "%", prefix + "%"),
                )
            else:
                cur.execute(
                    """
                    SELECT dedupe_key FROM posts WHERE dedupe_key IS NOT NULL
                    UNION
                    SELECT metadata->>'raw_version_key'
                    FROM posts
                    WHERE metadata->>'raw_version_key' IS NOT NULL
                    UNION
                    SELECT dedupe_key FROM discarded_post WHERE dedupe_key IS NOT NULL
                    """
                )
            return {row[0] for row in cur.fetchall() if row[0]}

    def get_cached_results_by_hashes(self, hashes: Iterable[str]) -> dict[str, dict]:
        """Bulk query already processed content hashes from posts and discarded_post."""
        hash_list = list(hashes)
        if not hash_list:
            return {}

        results = {}
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT metadata->>'content_hash', title, category, summary, 
                       university_name, school_name, major_name, content, metadata
                FROM posts
                WHERE metadata->>'content_hash' IN %s
                """,
                (tuple(hash_list),),
            )
            for row in cur.fetchall():
                h, title, category, summary, univ, school, major, content, metadata = row
                results[h] = {
                    "action": "keep",
                    "title": title,
                    "category": category,
                    "summary": summary,
                    "university_name": univ,
                    "school_name": school,
                    "major_name": major,
                    "content": content,
                    "metadata": metadata,
                }

            cur.execute(
                """
                SELECT metadata->>'content_hash', reason, metadata
                FROM discarded_post
                WHERE metadata->>'content_hash' IN %s
                """,
                (tuple(hash_list),),
            )
            for row in cur.fetchall():
                h, reason, metadata = row
                meta_dict = metadata if isinstance(metadata, dict) else json.loads(metadata)
                results[h] = {
                    "action": "irrelevant",
                    "reason": reason,
                    "llm_result_raw": meta_dict.get("llm_result"),
                }

        return results

    def mark_discarded(
        self,
        dedupe_key: str,
        source_type: str,
        title: str = "",
        source_url: str | None = None,
        reason: str = "irrelevant",
        metadata: dict | None = None,
    ) -> None:
        """标记一条记录为已丢弃，避免重复 LLM 处理。"""
        row = {
            "dedupe_key": dedupe_key,
            "source_type": source_type,
            "title": title,
            "source_url": source_url,
            "reason": reason,
            "metadata": json.dumps(metadata or {}, ensure_ascii=False),
        }
        with self.conn.cursor() as cur:
            cur.execute(UPSERT_DISCARDED_SQL, row)

    def mark_homepage_raw_processed(self, source_id: str, content_hash: str) -> None:
        if not source_id or not content_hash:
            return
        with self.conn.cursor() as cur:
            cur.execute(MARK_HOMEPAGE_RAW_PROCESSED_SQL, (source_id, content_hash))

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()

    def _build_school_faculty_source_row(
        self,
        extracted: dict,
        llm_result: LLMResult,
        post: Post | None,
        raw_version_key: str | None,
    ) -> dict | None:
        source_id = str(extracted.get("source_id") or "").strip()
        faculty_name = str(extracted.get("name") or "").strip()
        url = str(extracted.get("final_url") or extracted.get("requested_url") or "").strip()
        university_name = str(llm_result.university_name or extracted.get("university") or "").strip()
        if not source_id or not faculty_name or not url or not university_name:
            return None

        source_subtype = str(extracted.get("source_subtype") or "faculty").strip() or "faculty"
        university_code = _university_code_from_source(source_id)
        faculty_key = f"{university_code}:{_normalize_name(faculty_name)}"
        metadata = {
            "source_platform": "homepage",
            "extraction_method": "llm",
            "llm_result": llm_result.raw_response,
            "raw_version_key": raw_version_key,
            "post_dedupe_key": post.dedupe_key if post else None,
            "page_title": extracted.get("page_title"),
            "source_subtype": source_subtype,
        }
        return {
            "source_id": source_id,
            "source_batch": extracted.get("batch") or "unknown",
            "source_type": source_subtype,
            "university_code": university_code,
            "university_name": university_name,
            "unit_name": str(llm_result.school_name or "").strip() or None,
            "unit_type": _infer_unit_type(source_subtype),
            "faculty_name": faculty_name,
            "faculty_key": faculty_key,
            "url": url,
            "requested_url": extracted.get("requested_url") or None,
            "url_type": _infer_url_type(source_subtype),
            "is_primary": _is_primary_source(source_id),
            "status": "active",
            "metadata": json.dumps(metadata, ensure_ascii=False),
            "content_hash": extracted.get("content_hash") or None,
            "http_status": extracted.get("http_status"),
        }


def _normalize_name(value: str) -> str:
    return re.sub(r"\s+", "", value.strip())


def _university_code_from_source(source_id: str) -> str:
    return source_id.split("_", 1)[0].lower() or "unknown"


def _infer_unit_type(source_subtype: str) -> str:
    normalized = source_subtype.lower()
    if "lab" in normalized:
        return "lab"
    if "group" in normalized:
        return "group"
    if "school" in normalized:
        return "school"
    return "department"


def _infer_url_type(source_subtype: str) -> str:
    normalized = source_subtype.lower()
    if "lab" in normalized:
        return "lab_homepage"
    return "official_profile"


def _is_primary_source(source_id: str) -> bool:
    return source_id.endswith("_001")
