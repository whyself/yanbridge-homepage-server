"""从数据源 DB 读取原始记录。

XhsRawLoader:        PostgreSQL xhs_notes 表 (JOIN xhs_note_images)
HomepageRawLoader:   PostgreSQL homepage_raw_page 表
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator

import psycopg2
import psycopg2.extras

from .config import PipelineConfig
from .models import RawRecord, SourceType


# ---------------------------------------------------------------------------
# 抽象接口
# ---------------------------------------------------------------------------

class RawLoader(ABC):
    """从数据源 DB 读取未处理的原始记录。"""

    @abstractmethod
    def fetch_unprocessed(
        self, processed_dedupe_keys: set[str]
    ) -> Iterator[RawRecord]:
        """查询尚未写入 posts 表的原始记录。"""

    @abstractmethod
    def count_unprocessed(self, processed_dedupe_keys: set[str]) -> int:
        """统计待处理数量。"""

    @abstractmethod
    def close(self) -> None:
        """释放连接资源。"""


# ---------------------------------------------------------------------------
# PG 连接基类
# ---------------------------------------------------------------------------

class _PgLoader(RawLoader):
    """PostgreSQL loader 基类。"""

    def __init__(self, config: PipelineConfig):
        self.config = config
        self._conn: "psycopg2.extensions.connection | None" = None

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.config.database_url)
            self._conn.set_session(autocommit=True)
        return self._conn

    def _not_in_clause(self, column_expr: str, keys: set[str]) -> tuple[str, list]:
        """构建 NOT IN 子句。keys 为空时不添加过滤。"""
        if not keys:
            return "", []
        placeholders = ",".join(["%s"] * len(keys))
        return f" AND {column_expr} NOT IN ({placeholders})", list(keys)

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()


# ---------------------------------------------------------------------------
# XHS: PostgreSQL xhs_notes
# ---------------------------------------------------------------------------

class XhsRawLoader(_PgLoader):
    """从 PostgreSQL xhs_notes 表读取，同时 JOIN xhs_note_images。"""

    def fetch_unprocessed(
        self, processed_dedupe_keys: set[str]
    ) -> Iterator[RawRecord]:
        not_in, params = self._not_in_clause(
            "('xhs:note:' || n.note_id)", processed_dedupe_keys
        )
        sql = f"""
            SELECT n.*,
                   array_agg(
                       json_build_object(
                           'storage_key', i.storage_key,
                           'image_index', i.image_index,
                           'source_url', i.source_url
                       ) ORDER BY i.image_index
                   ) FILTER (WHERE i.id IS NOT NULL) AS images
            FROM xhs_notes n
            LEFT JOIN xhs_note_images i ON n.note_id = i.note_id
            WHERE 1=1 {not_in}
            GROUP BY n.id
            ORDER BY n.upload_time DESC
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            for row in cur:
                yield RawRecord(
                    source_type=SourceType.XIAOHONGSHU,
                    raw_data=dict(row),
                )

    def count_unprocessed(self, processed_dedupe_keys: set[str]) -> int:
        not_in, params = self._not_in_clause(
            "('xhs:note:' || note_id)", processed_dedupe_keys
        )
        sql = f"SELECT COUNT(*) FROM xhs_notes WHERE 1=1 {not_in}"
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]


# ---------------------------------------------------------------------------
# Homepage: PostgreSQL homepage_raw_page
# ---------------------------------------------------------------------------

class HomepageRawLoader(_PgLoader):
    """从 PostgreSQL homepage_raw_page 表读取。"""

    def _ensure_schema(self) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                ALTER TABLE homepage_raw_page
                ADD COLUMN IF NOT EXISTS pipeline_pending boolean NOT NULL DEFAULT false
                """
            )

    def fetch_unprocessed(
        self, processed_dedupe_keys: set[str]
    ) -> Iterator[RawRecord]:
        self._ensure_schema()
        not_in, params = self._not_in_clause(
            "('website:' || source_id || ':' || content_hash)", processed_dedupe_keys
        )
        sql = f"""
            SELECT * FROM homepage_raw_page
            WHERE status = 'success'
              AND pipeline_pending = true
              {not_in}
            ORDER BY fetched_at DESC
        """
        with self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            for row in cur:
                yield RawRecord(
                    source_type=SourceType.PERSONAL_WEBSITE,
                    raw_data=dict(row),
                )

    def count_unprocessed(self, processed_dedupe_keys: set[str]) -> int:
        self._ensure_schema()
        not_in, params = self._not_in_clause(
            "('website:' || source_id || ':' || content_hash)", processed_dedupe_keys
        )
        sql = (
            "SELECT COUNT(*) FROM homepage_raw_page "
            "WHERE status = 'success' "
            "AND pipeline_pending = true "
            f"{not_in}"
        )
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]
