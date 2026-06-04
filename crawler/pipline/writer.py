"""Post → PostgreSQL posts 表写入。

使用 psycopg2 直接 INSERT ... ON CONFLICT DO UPDATE。
"""

from __future__ import annotations

import json

import psycopg2
import psycopg2.extras

from .config import PipelineConfig
from .models import Post


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
