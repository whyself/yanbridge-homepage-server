import json
import os
import re
from typing import Iterable

from .models import UrlItem


CREATE_HOMEPAGE_SOURCES_SQL = """
CREATE TABLE IF NOT EXISTS homepage_sources (
    id bigserial PRIMARY KEY,
    source_id varchar(160) NOT NULL UNIQUE,
    batch varchar(64) NOT NULL,
    university_code varchar(32) NOT NULL,
    university_name varchar(128) NOT NULL,
    entity_type varchar(32) NOT NULL,
    entity_name varchar(160) NOT NULL,
    entity_key varchar(255) NOT NULL,
    url text NOT NULL,
    url_type varchar(32) NOT NULL DEFAULT 'unknown',
    is_primary boolean NOT NULL DEFAULT false,
    status varchar(32) NOT NULL DEFAULT 'active',
    http_status integer NULL,
    content_hash varchar(128) NULL,
    last_crawled_at timestamptz NULL,
    last_success_at timestamptz NULL,
    failure_count integer NOT NULL DEFAULT 0,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

CREATE_HOMEPAGE_SOURCES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_homepage_sources_university
ON homepage_sources (university_code, university_name);

CREATE INDEX IF NOT EXISTS ix_homepage_sources_entity
ON homepage_sources (university_code, entity_type, entity_key);

CREATE INDEX IF NOT EXISTS ix_homepage_sources_status
ON homepage_sources (status);

CREATE UNIQUE INDEX IF NOT EXISTS ux_homepage_sources_entity_url
ON homepage_sources (entity_key, url);
"""

UPSERT_HOMEPAGE_SOURCE_SQL = """
INSERT INTO homepage_sources (
    source_id, batch, university_code, university_name, entity_type,
    entity_name, entity_key, url, url_type, is_primary, status, metadata
) VALUES (
    %(source_id)s, %(batch)s, %(university_code)s, %(university_name)s, %(entity_type)s,
    %(entity_name)s, %(entity_key)s, %(url)s, %(url_type)s, %(is_primary)s, %(status)s, %(metadata)s
)
ON CONFLICT (source_id) DO UPDATE SET
    batch = EXCLUDED.batch,
    university_code = EXCLUDED.university_code,
    university_name = EXCLUDED.university_name,
    entity_type = EXCLUDED.entity_type,
    entity_name = EXCLUDED.entity_name,
    entity_key = EXCLUDED.entity_key,
    url = EXCLUDED.url,
    url_type = EXCLUDED.url_type,
    is_primary = EXCLUDED.is_primary,
    status = EXCLUDED.status,
    metadata = EXCLUDED.metadata,
    updated_at = now();
"""

UPDATE_HOMEPAGE_SOURCE_CRAWL_SQL = """
UPDATE homepage_sources
SET
    http_status = %(http_status)s,
    content_hash = %(content_hash)s,
    last_crawled_at = %(fetched_at)s,
    last_success_at = CASE
        WHEN %(status)s = 'success' THEN %(fetched_at)s
        ELSE last_success_at
    END,
    failure_count = CASE
        WHEN %(status)s = 'success' THEN 0
        ELSE failure_count + 1
    END,
    status = CASE
        WHEN status = 'removed' THEN status
        WHEN %(status)s = 'success' THEN 'active'
        ELSE 'failed'
    END,
    updated_at = now()
WHERE source_id = %(source_id)s;
"""

LOAD_ACTIVE_SOURCES_SQL = """
SELECT
    source_id AS id,
    batch,
    university_name AS university,
    CASE
        WHEN entity_type = 'research_group' THEN 'lab'
        ELSE 'faculty'
    END AS source_type,
    entity_name AS name,
    url,
    status
FROM homepage_sources
WHERE status IN ('active', 'failed')
ORDER BY status, failure_count, university_code, id
"""


def get_database_url() -> str:
    return _parse_database_url(
        os.environ.get(
            "DATABASE_URL",
            "postgresql://yanbridge:yanbridge@localhost:6542/yanbridge?sslmode=disable",
        )
    )


def ensure_homepage_sources_schema(database_url: str | None = None) -> None:
    import psycopg2

    with psycopg2.connect(database_url or get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_HOMEPAGE_SOURCES_SQL)
            cur.execute(CREATE_HOMEPAGE_SOURCES_INDEX_SQL)


def import_url_items_to_pg(items: Iterable[UrlItem], database_url: str | None = None) -> int:
    import psycopg2
    import psycopg2.extras

    rows = _dedupe_source_rows(_prepare_source_row(item) for item in items)
    if not rows:
        return 0

    with psycopg2.connect(database_url or get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_HOMEPAGE_SOURCES_SQL)
            cur.execute(CREATE_HOMEPAGE_SOURCES_INDEX_SQL)
            psycopg2.extras.execute_batch(cur, UPSERT_HOMEPAGE_SOURCE_SQL, rows)
    return len(rows)


def _dedupe_source_rows(rows: Iterable[dict]) -> list[dict]:
    """Drop duplicate rows that point the same entity at the same URL.

    Some JSONL pools contain repeated URLs with different legacy source_id
    suffixes. The source table intentionally keeps one row per entity+URL.
    """
    deduped: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["entity_key"], row["url"])
        existing = deduped.get(key)
        if existing is None:
            deduped[key] = row
            continue
        if row.get("is_primary") and not existing.get("is_primary"):
            deduped[key] = row
    return list(deduped.values())


def load_active_url_items_from_pg(limit: int | None = None, database_url: str | None = None) -> list[UrlItem]:
    import psycopg2
    import psycopg2.extras

    ensure_homepage_sources_schema(database_url)
    sql = LOAD_ACTIVE_SOURCES_SQL
    params: tuple[int, ...] = ()
    if limit is not None:
        sql += "\nLIMIT %s"
        params = (limit,)

    with psycopg2.connect(database_url or get_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [UrlItem.from_dict(dict(row)) for row in cur.fetchall()]


def update_source_crawl_state(rows: Iterable[dict], database_url: str | None = None) -> int:
    import psycopg2
    import psycopg2.extras

    prepared_rows = [
        {
            "source_id": row.get("source_id"),
            "status": row.get("status"),
            "http_status": row.get("http_status"),
            "content_hash": row.get("content_hash"),
            "fetched_at": row.get("fetched_at"),
        }
        for row in rows
        if row.get("source_id")
    ]
    if not prepared_rows:
        return 0

    ensure_homepage_sources_schema(database_url)
    with psycopg2.connect(database_url or get_database_url()) as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, UPDATE_HOMEPAGE_SOURCE_CRAWL_SQL, prepared_rows)
    return len(prepared_rows)


def _prepare_source_row(item: UrlItem) -> dict:
    university_code = _university_code_from_source(item)
    entity_type = _entity_type_from_source_type(item.source_type)
    entity_name = _normalize_entity_name(item.name)
    return {
        "source_id": item.id,
        "batch": item.batch,
        "university_code": university_code,
        "university_name": item.university,
        "entity_type": entity_type,
        "entity_name": entity_name,
        "entity_key": f"{university_code}:{entity_type}:{entity_name}",
        "url": item.url,
        "url_type": "lab_homepage" if entity_type == "research_group" else "unknown",
        "is_primary": item.id.endswith("_001"),
        "status": item.status,
        "metadata": json.dumps(
            {
                "legacy_source_type": item.source_type,
                "imported_from": "jsonl",
            },
            ensure_ascii=False,
        ),
    }


def _university_code_from_source(item: UrlItem) -> str:
    if "_" in item.id:
        return item.id.split("_", 1)[0]
    if "_" in item.batch:
        return item.batch.split("_", 1)[0]
    return item.university.lower().strip()


def _entity_type_from_source_type(source_type: str) -> str:
    if source_type == "lab":
        return "research_group"
    return "faculty"


def _normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", "", name.strip())


def _parse_database_url(url: str) -> str:
    return re.sub(r"^postgresql\+[^:]+://", "postgresql://", url)
