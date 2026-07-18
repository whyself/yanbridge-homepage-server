"""Safe tools for the standalone homepage agent.

The agent can call these tool names, but it never receives raw SQL access.
"""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

import psycopg2
import psycopg2.extras

from .config import AgentConfig
from .models import PostDraft


class AgentTools:
    def __init__(self, config: AgentConfig | None = None):
        self.config = config or AgentConfig()
        self._conn: psycopg2.extensions.connection | None = None

    def close(self) -> None:
        if self._conn and not self._conn.closed:
            self._conn.close()

    def crw_search(self, query: str, limit: int = 5) -> dict[str, Any]:
        data = self._post_crw("/v1/search", {"query": query, "limit": limit})
        raw_items = data.get("data") or data.get("results") or []
        if isinstance(raw_items, dict):
            raw_items = raw_items.get("results") or raw_items.get("data") or []
        results = []
        for item in raw_items[:limit]:
            if isinstance(item, dict):
                results.append(
                    {
                        "title": str(item.get("title") or ""),
                        "url": str(item.get("url") or item.get("link") or ""),
                        "description": str(item.get("description") or item.get("snippet") or ""),
                    }
                )
        return {"results": results}

    def crw_scrape(self, url: str) -> dict[str, Any]:
        data = self._post_crw("/v1/scrape", {"url": url})
        body = data.get("data") if isinstance(data.get("data"), dict) else data
        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        return {
            "url": str(body.get("url") or body.get("sourceURL") or url),
            "title": str(metadata.get("title") or body.get("title") or ""),
            "markdown": str(body.get("markdown") or ""),
            "text": str(body.get("text") or body.get("content") or ""),
            "metadata": metadata,
        }

    def find_post(
        self,
        dedupe_key: str = "",
        source_url: str = "",
        university_name: str = "",
        school_name: str = "",
        teacher_name: str = "",
        keyword: str = "",
        limit: int = 10,
    ) -> dict[str, Any]:
        clauses = ["deleted_at IS NULL"]
        params: list[Any] = []
        if dedupe_key:
            clauses.append("dedupe_key = %s")
            params.append(dedupe_key)
        if source_url:
            clauses.append("source_url = %s")
            params.append(source_url)
        if university_name:
            clauses.append("university_name ILIKE %s")
            params.append(f"%{university_name}%")
        if school_name:
            clauses.append("school_name ILIKE %s")
            params.append(f"%{school_name}%")
        if teacher_name:
            like = f"%{teacher_name}%"
            clauses.append("(title ILIKE %s OR summary ILIKE %s OR metadata->>'teacher_name' ILIKE %s)")
            params.extend([like, like, like])
        if keyword:
            like = f"%{keyword}%"
            clauses.append("(title ILIKE %s OR summary ILIKE %s OR content ILIKE %s)")
            params.extend([like, like, like])

        limit = max(1, min(int(limit), 50))
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
            return {"matches": [_normalize_row(dict(row)) for row in cur.fetchall()]}

    def update_post(self, draft: dict[str, Any]) -> dict[str, Any]:
        post = PostDraft(**draft)
        now = datetime.now(timezone.utc).isoformat()
        dedupe_key = post.dedupe_key or _make_dedupe_key(post)
        metadata = dict(post.metadata)
        metadata.setdefault("source_platform", "homepage_agent")
        if post.teacher_name_cn:
            metadata["teacher_name_cn"] = post.teacher_name_cn
            metadata.setdefault("teacher_name", post.teacher_name_cn)
        if post.teacher_name_en:
            metadata["teacher_name_en"] = post.teacher_name_en
            metadata.setdefault("teacher_name", post.teacher_name_en)
        if post.evidence:
            metadata["evidence"] = _only_urls(post.evidence)

        row = {
            "source_type": "personal_website",
            "post_type": "crawled_post",
            "title": post.title,
            "category": "mentor_recruitment",
            "status": "published",
            "author_user_id": None,
            "summary": post.summary or None,
            "content": post.content or None,
            "university_name": post.university_name or None,
            "school_name": post.school_name or None,
            "major_name": post.major_name or None,
            "source_url": post.source_url or None,
            "dedupe_key": dedupe_key,
            "metadata": json.dumps(metadata, ensure_ascii=False),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        with self.conn.cursor() as cur:
            cur.execute(_UPSERT_POST_SQL, row)
        return {"post": self.find_post(dedupe_key=dedupe_key, limit=1)["matches"][0]}

    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name == "crw_search":
            return self.crw_search(**args)
        if name == "crw_scrape":
            return self.crw_scrape(**args)
        if name == "find_post":
            return self.find_post(**args)
        if name == "update_post":
            return self.update_post(args)
        raise ValueError(f"Unknown tool: {name}")

    @property
    def conn(self):
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(self.config.database_url)
            self._conn.set_session(autocommit=True)
        return self._conn

    def _post_crw(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.config.crw_api_url}{path}"
        headers = {"Content-Type": "application/json"}
        if self.config.crw_api_key:
            headers["Authorization"] = f"Bearer {self.config.crw_api_key}"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.crw_timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"CRW {path} failed: HTTP {exc.code} {detail}") from exc


def tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "crw_search",
                "description": "Search web pages with CRW.",
                "parameters": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 5}},
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "crw_scrape",
                "description": "Scrape one URL with CRW.",
                "parameters": {
                    "type": "object",
                    "properties": {"url": {"type": "string"}},
                    "required": ["url"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "find_post",
                "description": "Find existing posts safely. No SQL input.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "dedupe_key": {"type": "string"},
                        "source_url": {"type": "string"},
                        "university_name": {"type": "string"},
                        "school_name": {"type": "string"},
                        "teacher_name": {"type": "string"},
                        "keyword": {"type": "string"},
                        "limit": {"type": "integer", "default": 10},
                    },
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "update_post",
                "description": "Create or update a post from structured fields.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "summary": {"type": "string"},
                        "university_name": {"type": "string"},
                        "school_name": {"type": "string"},
                        "major_name": {"type": "string"},
                        "source_url": {"type": "string"},
                        "dedupe_key": {"type": "string"},
                        "teacher_name_cn": {"type": "string"},
                        "teacher_name_en": {"type": "string"},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "metadata": {"type": "object"},
                    },
                    "required": ["title"],
                },
            },
        },
    ]


_UPSERT_POST_SQL = """
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


def _make_dedupe_key(post: PostDraft) -> str:
    seed = post.source_url or "|".join([post.university_name, post.school_name, post.title])
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]
    return f"agent:homepage:{digest}"


def _only_urls(values: list[str]) -> list[str]:
    return [value for value in values if value.startswith(("http://", "https://"))]


def _normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    metadata = row.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {"raw_metadata": metadata}
    row["metadata"] = metadata
    for key in ("created_at", "updated_at"):
        value = row.get(key)
        if hasattr(value, "isoformat"):
            row[key] = value.isoformat()
    return row

