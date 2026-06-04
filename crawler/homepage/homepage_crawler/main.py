import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from .config import DEFAULT_CONCURRENCY, DEFAULT_LOG_DIR, DEFAULT_TIMEOUT_MS
from .crawler import crawl_items
from .failure_log import save_failed_url_log
from .pg_store import load_existing_raw_rows_from_pg, save_raw_rows_to_pg
from .source_store import load_active_url_items_from_pg, update_source_crawl_state
from .update_detector import DEFAULT_DIFF_CHAR_THRESHOLD, decide_updates, summarize_decisions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crawl homepage URLs from PostgreSQL into PostgreSQL raw rows.")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument(
        "--update-diff-chars",
        type=int,
        default=DEFAULT_DIFF_CHAR_THRESHOLD,
        help="Minimum changed normalized text characters to count as an effective homepage update.",
    )
    parser.add_argument(
        "--no-pg",
        action="store_true",
        help="Do not write homepage raw rows to PostgreSQL.",
    )
    return parser.parse_args()


async def amain() -> None:
    args = parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    items = load_active_url_items_from_pg(args.limit)
    if not items:
        raise ValueError("No crawlable homepage URL items found in homepage_sources")

    old_rows = load_existing_raw_rows_from_pg()
    rows = await crawl_items(items, run_id, args.timeout_ms, args.concurrency)
    update_decisions = decide_updates(old_rows, rows, args.update_diff_chars)
    update_summary = summarize_decisions(update_decisions)
    row_by_source_id = {row.get("source_id"): row for row in rows}
    decision_by_source_id = {decision.source_id: decision for decision in update_decisions}
    for decision in update_decisions:
        if decision.status in {"low_diff", "unchanged"}:
            continue
        row = row_by_source_id.get(decision.source_id, {})
        diff_chars = "n/a" if decision.diff_chars is None else str(decision.diff_chars)
        print(
            "homepage_update "
            f"source_id={decision.source_id} "
            f"name={row.get('name', '')} "
            f"status={decision.status} "
            f"diff_chars={diff_chars}"
        )
    for row in rows:
        decision = decision_by_source_id.get(row.get("source_id"))
        if not decision:
            continue
        row["diff_chars"] = decision.diff_chars
        row["update_status"] = decision.status
        row["pipeline_pending"] = decision.status in {"new", "changed"}
    source_state_count = update_source_crawl_state(rows)
    pg_saved_count = 0
    if not args.no_pg:
        pg_saved_count = save_raw_rows_to_pg(rows)
    failed_log_path = save_failed_url_log(args.log_dir, run_id, rows)

    success_count = sum(1 for row in rows if row["status"] == "success")
    print(f"run_id={run_id} total={len(rows)} success={success_count} failed={len(rows) - success_count}")
    print(
        "homepage_updates "
        f"diff_chars_threshold={args.update_diff_chars} "
        f"effective={update_summary.effective_updates} "
        f"new={update_summary.new} "
        f"changed={update_summary.changed} "
        f"low_diff={update_summary.low_diff} "
        f"unchanged={update_summary.unchanged} "
        f"failed={update_summary.failed} "
        f"pg_saved={pg_saved_count} "
        f"source_state_updated={source_state_count}"
    )
    if failed_log_path:
        print(f"failed_url_log={failed_log_path}")


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
