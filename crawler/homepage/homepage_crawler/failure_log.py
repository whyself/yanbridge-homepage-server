import json
from pathlib import Path


FAILED_URL_FIELDS = (
    "run_id",
    "source_id",
    "batch",
    "university",
    "source_type",
    "name",
    "requested_url",
    "final_url",
    "http_status",
    "error_type",
    "error_message",
)


def save_failed_url_log(log_dir: Path, run_id: str, rows: list[dict]) -> Path | None:
    failed_rows = [row for row in rows if row["status"] == "failed"]
    if not failed_rows:
        return None

    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"failed_urls_{run_id}.jsonl"
    with log_path.open("w", encoding="utf-8") as file:
        for row in failed_rows:
            payload = {field: row.get(field) for field in FAILED_URL_FIELDS}
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return log_path
