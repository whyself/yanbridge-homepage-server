from pathlib import Path
import sqlite3


def load_existing_raw_rows(db_path: Path) -> dict[str, dict]:
    if not db_path.exists():
        return {}
    with sqlite3.connect(db_path) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """
            SELECT source_id, status, content_hash, text, markdown, fetched_at
            FROM homepage_raw_page
            """
        ).fetchall()
    return {row["source_id"]: dict(row) for row in rows}


UPSERT_RAW_SQL = """
INSERT INTO homepage_raw_page (
    run_id, source_id, batch, university, source_type, name,
    requested_url, final_url, http_status, status, fetched_at,
    page_title, markdown, text, content_hash, error_type, error_message
) VALUES (
    :run_id, :source_id, :batch, :university, :source_type, :name,
    :requested_url, :final_url, :http_status, :status, :fetched_at,
    :page_title, :markdown, :text, :content_hash, :error_type, :error_message
)
ON CONFLICT(source_id) DO UPDATE SET
    run_id = excluded.run_id,
    batch = excluded.batch,
    university = excluded.university,
    source_type = excluded.source_type,
    name = excluded.name,
    requested_url = excluded.requested_url,
    final_url = excluded.final_url,
    http_status = excluded.http_status,
    status = excluded.status,
    fetched_at = excluded.fetched_at,
    page_title = excluded.page_title,
    markdown = excluded.markdown,
    text = excluded.text,
    content_hash = excluded.content_hash,
    error_type = excluded.error_type,
    error_message = excluded.error_message;
"""


def save_raw_rows(db_path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with sqlite3.connect(db_path) as db:
        db.executemany(UPSERT_RAW_SQL, rows)
        db.commit()
