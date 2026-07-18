"""CLI runner for the Pydantic AI academic builder."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any

from .academic_agent import build_academic_extractor, extract_academic_page
from .academic_resolver import resolve_academic_extraction
from .academic_schemas import AcademicAgentResult, AcademicExtraction, HomepageRawRow
from .academic_tools import AcademicRepository
from .config import PipelineConfig


TASK_TYPE = "academic_builder"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build academic graph from homepage_raw_page with Pydantic AI.")
    parser.add_argument("--limit", type=int, default=0, help="Limit raw rows. 0 means all unprocessed rows.")
    parser.add_argument("--source-id", default="", help="Run a single source_id.")
    parser.add_argument("--include-processed", action="store_true", help="Do not skip existing agent_runs.")
    parser.add_argument("--dry-run", action="store_true", help="Run model/tools without writing academic tables.")
    parser.add_argument("--max-text-chars", type=int, default=8000, help="Raw page text chars passed to the extractor.")
    parser.add_argument("--model", default="", help="Override AGENT_MODEL, e.g. deepseek:deepseek-chat.")
    parser.add_argument("--workers", type=int, default=1, help="Concurrent model extraction workers. Max 2500.")
    parser.add_argument("--jsonl-output", default="", help="Optional path to write per-row result JSONL.")
    return parser.parse_args()


async def amain() -> None:
    _load_server_env()
    args = parse_args()
    config = PipelineConfig()
    if args.model:
        config.agent_model = args.model
    workers = max(1, args.workers)
    if workers > 2500:
        raise SystemExit("--workers must be <= 2500")
    if workers > 100:
        print(f"academic_agent_warning workers={workers} exceeds recommended concurrency 100", flush=True)

    repo = AcademicRepository(config, dry_run=args.dry_run)
    extractor = build_academic_extractor(config)
    rows = repo.load_raw_rows(
        limit=args.limit,
        source_id=args.source_id,
        include_processed=args.include_processed,
        task_type=TASK_TYPE,
    )
    print(
        "academic_agent_start "
        f"rows={len(rows)} dry_run={args.dry_run} "
        f"include_processed={args.include_processed} workers={workers} "
        f"model={config.agent_model or config.deepseek_model}"
    )
    if not rows:
        repo.close()
        return

    output_file = open(args.jsonl_output, "a", encoding="utf-8") if args.jsonl_output else None
    stats = {"succeeded": 0, "skipped": 0, "failed": 0}
    total_usage: dict[str, int] = {
        "requests": 0,
        "tool_calls": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_write_tokens": 0,
        "cache_read_tokens": 0,
    }
    merged_institutions: list[dict[str, Any]] = []
    try:
        async for index, raw, extraction, usage, exc in _iter_extractions(
            extractor,
            rows,
            max_text_chars=args.max_text_chars,
            workers=workers,
        ):
            print(f"[{index}/{len(rows)}] {raw.source_id} {raw.source_type} {raw.name}", flush=True)
            if exc is None and extraction is not None:
                try:
                    result, actions = resolve_academic_extraction(repo, raw, extraction)
                except Exception as resolve_exc:
                    actions = []
                    result = AcademicAgentResult(
                        status="failed",
                        confidence=0,
                        summary="Academic extraction/resolution failed.",
                        reason=f"{type(resolve_exc).__name__}: {resolve_exc}",
                    )
            else:
                actions = []
                result = AcademicAgentResult(
                    status="failed",
                    confidence=0,
                    summary="Academic extraction/resolution failed.",
                    reason=f"{type(exc).__name__}: {exc}",
                )
            stats[result.status] += 1
            _add_usage(total_usage, usage)
            if not args.dry_run:
                repo.save_agent_run(
                    raw,
                    result,
                    actions,
                    config.agent_model or config.deepseek_model,
                    usage,
                    TASK_TYPE,
                )
            line = {
                "source_id": raw.source_id,
                "name": raw.name,
                "source_type": raw.source_type,
                "url": raw.url,
                "extraction": extraction.model_dump() if extraction is not None else None,
                "result": result.model_dump(),
                "usage": usage,
                "actions": actions,
            }
            print(_one_line_summary(line), flush=True)
            if output_file:
                output_file.write(json.dumps(line, ensure_ascii=False) + "\n")
                output_file.flush()
        if not args.dry_run:
            merged_institutions = repo.merge_duplicate_institutions()
            if merged_institutions:
                print(f"academic_agent_cleanup merged_institutions={len(merged_institutions)}", flush=True)
    finally:
        if output_file:
            output_file.close()
        repo.close()

    print(
        "academic_agent_done "
        f"succeeded={stats['succeeded']} skipped={stats['skipped']} failed={stats['failed']} "
        f"requests={total_usage['requests']} tool_calls={total_usage['tool_calls']} "
        f"input_tokens={total_usage['input_tokens']} output_tokens={total_usage['output_tokens']} "
        f"cache_read_tokens={total_usage['cache_read_tokens']} "
        f"merged_institutions={len(merged_institutions)}"
    )


async def _iter_extractions(
    extractor: Any,
    rows: list[HomepageRawRow],
    max_text_chars: int,
    workers: int,
):
    semaphore = asyncio.Semaphore(workers)

    async def run_one(raw: HomepageRawRow) -> tuple[HomepageRawRow, AcademicExtraction | None, dict[str, int], Exception | None]:
        async with semaphore:
            try:
                extraction, usage = await extract_academic_page(extractor, raw, max_text_chars)
                return raw, extraction, usage, None
            except Exception as exc:
                return raw, None, {}, exc

    tasks = [asyncio.create_task(run_one(raw)) for raw in rows]
    for index, task in enumerate(asyncio.as_completed(tasks), start=1):
        raw, extraction, usage, exc = await task
        yield index, raw, extraction, usage, exc


def _one_line_summary(value: dict[str, Any]) -> str:
    result = value["result"]
    return (
        "academic_agent_result "
        f"source_id={value['source_id']} "
        f"status={result['status']} "
        f"confidence={result['confidence']} "
        f"created_post={result['created_post']} "
        f"summary={result['summary'][:120]}"
    )

def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key in total:
        total[key] += int(usage.get(key) or 0)


def _load_server_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    server_env = Path(__file__).resolve().parents[2] / ".env"
    if server_env.exists():
        load_dotenv(server_env, override=False)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
