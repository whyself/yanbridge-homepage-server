from pathlib import Path
import sqlite3


RAW_TABLE_NAME = "homepage_raw_page"

RAW_TABLE_COLUMNS = (
    ("id", "INTEGER", 0, None, 1),
    ("run_id", "TEXT", 1, None, 0),
    ("source_id", "TEXT", 1, None, 0),
    ("batch", "TEXT", 1, None, 0),
    ("university", "TEXT", 1, None, 0),
    ("source_type", "TEXT", 1, None, 0),
    ("name", "TEXT", 1, None, 0),
    ("requested_url", "TEXT", 1, None, 0),
    ("final_url", "TEXT", 0, None, 0),
    ("http_status", "INTEGER", 0, None, 0),
    ("status", "TEXT", 1, None, 0),
    ("fetched_at", "TEXT", 1, None, 0),
    ("page_title", "TEXT", 0, None, 0),
    ("markdown", "TEXT", 0, None, 0),
    ("text", "TEXT", 0, None, 0),
    ("content_hash", "TEXT", 0, None, 0),
    ("error_type", "TEXT", 0, None, 0),
    ("error_message", "TEXT", 0, None, 0),
)

CREATE_RAW_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS homepage_raw_page (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    source_id TEXT NOT NULL,
    batch TEXT NOT NULL,
    university TEXT NOT NULL,
    source_type TEXT NOT NULL,
    name TEXT NOT NULL,
    requested_url TEXT NOT NULL,
    final_url TEXT,
    http_status INTEGER,
    status TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    page_title TEXT,
    markdown TEXT,
    text TEXT,
    content_hash TEXT,
    error_type TEXT,
    error_message TEXT
);
"""

CREATE_UNIQUE_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_homepage_raw_page_source_id
ON homepage_raw_page(source_id);
"""


CREATE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_homepage_raw_page_source_time
ON homepage_raw_page(source_id, fetched_at);
"""


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as db:
        db.execute(CREATE_RAW_TABLE_SQL)
        db.execute(CREATE_UNIQUE_INDEX_SQL)
        db.execute(CREATE_INDEX_SQL)
        db.commit()


def validate_raw_schema(db_path: Path) -> None:
    with sqlite3.connect(db_path) as db:
        columns = db.execute(f"PRAGMA table_info({RAW_TABLE_NAME})").fetchall()
        actual_columns = tuple((row[1], row[2], row[3], row[4], row[5]) for row in columns)
        if actual_columns != RAW_TABLE_COLUMNS:
            raise RuntimeError(f"{RAW_TABLE_NAME} schema does not match docs/homepage-raw-page-schema.md")

        indexes = {
            row[1]: row[2]
            for row in db.execute(f"PRAGMA index_list({RAW_TABLE_NAME})").fetchall()
        }
        if indexes.get("idx_homepage_raw_page_source_id") != 1:
            raise RuntimeError("missing unique index idx_homepage_raw_page_source_id")
        if "idx_homepage_raw_page_source_time" not in indexes:
            raise RuntimeError("missing index idx_homepage_raw_page_source_time")

        source_id_index_columns = _index_columns(db, "idx_homepage_raw_page_source_id")
        if source_id_index_columns != ("source_id",):
            raise RuntimeError("idx_homepage_raw_page_source_id must index source_id")

        source_time_index_columns = _index_columns(db, "idx_homepage_raw_page_source_time")
        if source_time_index_columns != ("source_id", "fetched_at"):
            raise RuntimeError("idx_homepage_raw_page_source_time must index source_id, fetched_at")


def _index_columns(db: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    rows = db.execute(f"PRAGMA index_info({index_name})").fetchall()
    return tuple(row[2] for row in rows)
