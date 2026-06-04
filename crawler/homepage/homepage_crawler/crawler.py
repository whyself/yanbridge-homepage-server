import asyncio
import hashlib
import re
from datetime import datetime, timezone
from typing import Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

from .models import UrlItem


def _markdown_to_text(markdown: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", markdown)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_`~-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _markdown_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for attr in ("fit_markdown", "raw_markdown", "markdown"):
        attr_value = getattr(value, attr, None)
        if isinstance(attr_value, str):
            return attr_value
    return str(value)


def _get_metadata(result: Any) -> dict:
    metadata = getattr(result, "metadata", None)
    return metadata if isinstance(metadata, dict) else {}


async def crawl_items(items: list[UrlItem], run_id: str, timeout_ms: int, concurrency: int) -> list[dict]:
    browser_config = BrowserConfig(headless=True, verbose=False)
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, page_timeout=timeout_ms)
    semaphore = asyncio.Semaphore(concurrency)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        total = len(items)
        tasks = [
            _crawl_one(crawler, run_config, semaphore, item, run_id, index, total)
            for index, item in enumerate(items, start=1)
        ]
        return await asyncio.gather(*tasks)


async def _crawl_one(
    crawler: AsyncWebCrawler,
    run_config: CrawlerRunConfig,
    semaphore: asyncio.Semaphore,
    item: UrlItem,
    run_id: str,
    index: int,
    total: int,
) -> dict:
    fetched_at = datetime.now(timezone.utc).isoformat()
    async with semaphore:
        try:
            result = await crawler.arun(url=str(item.url), config=run_config)
            markdown = _markdown_value(getattr(result, "markdown", ""))
            text = _markdown_to_text(markdown)
            metadata = _get_metadata(result)
            success = bool(getattr(result, "success", bool(markdown)))
            error_message = getattr(result, "error_message", None)

            row = {
                "run_id": run_id,
                "source_id": item.id,
                "batch": item.batch,
                "university": item.university,
                "source_type": item.source_type,
                "name": item.name,
                "requested_url": str(item.url),
                "final_url": getattr(result, "redirected_url", None) or getattr(result, "url", str(item.url)),
                "http_status": getattr(result, "status_code", None),
                "status": "success" if success else "failed",
                "fetched_at": fetched_at,
                "page_title": metadata.get("title", ""),
                "markdown": markdown,
                "text": text,
                "content_hash": hashlib.sha256(markdown.encode("utf-8")).hexdigest() if markdown else "",
                "error_type": None if success else "CrawlError",
                "error_message": None if success else error_message,
            }
            print(f"[{index}/{total}] {row['status']} {item.name} {item.url}", flush=True)
            return row
        except Exception as exc:
            row = {
                "run_id": run_id,
                "source_id": item.id,
                "batch": item.batch,
                "university": item.university,
                "source_type": item.source_type,
                "name": item.name,
                "requested_url": str(item.url),
                "final_url": None,
                "http_status": None,
                "status": "failed",
                "fetched_at": fetched_at,
                "page_title": "",
                "markdown": "",
                "text": "",
                "content_hash": "",
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
            print(f"[{index}/{total}] failed {item.name} {item.url}", flush=True)
            return row
