import os
import re
from typing import Iterable


CREATE_HOMEPAGE_RAW_PAGE_SQL = """
CREATE TABLE IF NOT EXISTS homepage_raw_page (
    id bigserial PRIMARY KEY,
    run_id text NOT NULL,
    source_id text NOT NULL,
    batch text NOT NULL,
    university text NOT NULL,
    source_type text NOT NULL,
    name text NOT NULL,
    requested_url text NOT NULL,
    final_url text NULL,
    http_status integer NULL,
    status text NOT NULL,
    fetched_at timestamptz NOT NULL,
    page_title text NULL,
    markdown text NULL,
    text text NULL,
    content_hash text NOT NULL,
    error_type text NULL,
    error_message text NULL,
    diff_chars integer NULL,
    update_status varchar(32) NOT NULL DEFAULT 'changed',
    pipeline_pending boolean NOT NULL DEFAULT false,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

MIGRATE_HOMEPAGE_RAW_PAGE_SQL = """
ALTER TABLE homepage_raw_page
ADD COLUMN IF NOT EXISTS pipeline_pending boolean NOT NULL DEFAULT false;
"""

CREATE_HOMEPAGE_RAW_PAGE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS ux_homepage_raw_page_source_id
ON homepage_raw_page(source_id);
"""

CREATE_HOMEPAGE_RAW_PAGE_SOURCE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_homepage_raw_page_source_time
ON homepage_raw_page(source_id, fetched_at DESC);
"""

LOAD_LATEST_HOMEPAGE_RAW_ROWS_SQL = """
SELECT DISTINCT ON (source_id)
    source_id, status, content_hash, text, markdown, fetched_at
FROM homepage_raw_page
ORDER BY source_id, fetched_at DESC;
"""

UPSERT_HOMEPAGE_RAW_PAGE_SQL = """
INSERT INTO homepage_raw_page (
    run_id, source_id, batch, university, source_type, name,
    requested_url, final_url, http_status, status, fetched_at,
    page_title, markdown, text, content_hash, error_type, error_message,
    diff_chars, update_status, pipeline_pending, metadata
) VALUES (
    %(run_id)s, %(source_id)s, %(batch)s, %(university)s, %(source_type)s, %(name)s,
    %(requested_url)s, %(final_url)s, %(http_status)s, %(status)s, %(fetched_at)s,
    %(page_title)s, %(markdown)s, %(text)s, %(content_hash)s, %(error_type)s, %(error_message)s,
    %(diff_chars)s, %(update_status)s, %(pipeline_pending)s, %(metadata)s
)
ON CONFLICT (source_id) DO UPDATE SET
    run_id = EXCLUDED.run_id,
    batch = EXCLUDED.batch,
    university = EXCLUDED.university,
    source_type = EXCLUDED.source_type,
    name = EXCLUDED.name,
    requested_url = EXCLUDED.requested_url,
    final_url = EXCLUDED.final_url,
    http_status = EXCLUDED.http_status,
    status = EXCLUDED.status,
    fetched_at = EXCLUDED.fetched_at,
    page_title = EXCLUDED.page_title,
    markdown = EXCLUDED.markdown,
    text = EXCLUDED.text,
    content_hash = EXCLUDED.content_hash,
    error_type = EXCLUDED.error_type,
    error_message = EXCLUDED.error_message,
    diff_chars = EXCLUDED.diff_chars,
    update_status = EXCLUDED.update_status,
    pipeline_pending = homepage_raw_page.pipeline_pending OR EXCLUDED.pipeline_pending,
    metadata = EXCLUDED.metadata,
    updated_at = now();
"""


def get_database_url() -> str:
    return _parse_database_url(
        os.environ.get(
            "DATABASE_URL",
            "postgresql://yanbridge:yanbridge@localhost:6542/yanbridge?sslmode=disable",
        )
    )


def save_raw_rows_to_pg(
    rows: Iterable[dict],
    database_url: str | None = None,
) -> int:
    prepared_rows = [_prepare_row(row) for row in rows if row.get("source_id")]
    if not prepared_rows:
        return 0

    import psycopg2
    import psycopg2.extras

    with psycopg2.connect(database_url or get_database_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_HOMEPAGE_RAW_PAGE_SQL)
            cur.execute(MIGRATE_HOMEPAGE_RAW_PAGE_SQL)
            cur.execute(CREATE_HOMEPAGE_RAW_PAGE_INDEX_SQL)
            cur.execute(CREATE_HOMEPAGE_RAW_PAGE_SOURCE_INDEX_SQL)
            psycopg2.extras.execute_batch(cur, UPSERT_HOMEPAGE_RAW_PAGE_SQL, prepared_rows)
    return len(prepared_rows)


def save_effective_raw_rows_to_pg(
    rows: Iterable[dict],
    database_url: str | None = None,
) -> int:
    return save_raw_rows_to_pg(rows, database_url)


def load_existing_raw_rows_from_pg(database_url: str | None = None) -> dict[str, dict]:
    import psycopg2
    import psycopg2.extras

    with psycopg2.connect(database_url or get_database_url()) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(CREATE_HOMEPAGE_RAW_PAGE_SQL)
            cur.execute(MIGRATE_HOMEPAGE_RAW_PAGE_SQL)
            cur.execute(CREATE_HOMEPAGE_RAW_PAGE_INDEX_SQL)
            cur.execute(CREATE_HOMEPAGE_RAW_PAGE_SOURCE_INDEX_SQL)
            cur.execute(LOAD_LATEST_HOMEPAGE_RAW_ROWS_SQL)
            rows = cur.fetchall()
    return {row["source_id"]: dict(row) for row in rows}


def _prepare_row(row: dict) -> dict:
    prepared = dict(row)
    prepared["diff_chars"] = row.get("diff_chars")
    prepared["update_status"] = row.get("update_status") or "changed"
    prepared["pipeline_pending"] = bool(row.get("pipeline_pending"))
    prepared["metadata"] = row.get("metadata") or "{}"
    return prepared


def _parse_database_url(url: str) -> str:
    return re.sub(r"^postgresql\+[^:]+://", "postgresql://", url)
