#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="./logs"
mkdir -p "$LOG_DIR"
TIMESTAMP="$(date +"%Y%m%d_%H%M%S")"
LOG_FILE="$LOG_DIR/homepage_${TIMESTAMP}.log"

IMPORT_SOURCES=false
RUN_CRAWL=true
RUN_PIPELINE=true
CRAWL_LIMIT=""
PIPELINE_LIMIT=""
UPDATE_DIFF_CHARS="10"
CONCURRENCY="2"

usage() {
  cat <<'EOF'
Usage:
  scripts/run_once.sh [options]

Options:
  --import                   Import JSONL config into homepage_sources before running.
  --import-only              Import JSONL only, then exit.
  --no-crawl                 Skip crawler.
  --no-pipeline              Skip pipeline.
  --crawl-limit N            Limit crawler URL count.
  --pipeline-limit N         Limit pipeline raw record count.
  --update-diff-chars N      Effective update threshold. Default: 10.
  --concurrency N            Crawler concurrency. Default: 2.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --import)
      IMPORT_SOURCES=true
      shift
      ;;
    --import-only)
      IMPORT_SOURCES=true
      RUN_CRAWL=false
      RUN_PIPELINE=false
      shift
      ;;
    --no-crawl)
      RUN_CRAWL=false
      shift
      ;;
    --no-pipeline)
      RUN_PIPELINE=false
      shift
      ;;
    --crawl-limit)
      CRAWL_LIMIT="$2"
      shift 2
      ;;
    --pipeline-limit)
      PIPELINE_LIMIT="$2"
      shift 2
      ;;
    --update-diff-chars)
      UPDATE_DIFF_CHARS="$2"
      shift 2
      ;;
    --concurrency)
      CONCURRENCY="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

run_logged() {
  log "RUN: $*"
  "$@" >>"$LOG_FILE" 2>&1
}

log "====== homepage server run started ======"

if [[ "$IMPORT_SOURCES" == true ]]; then
  run_logged docker compose run --rm homepage-crawler \
    uv run python -m homepage_crawler.import_sources
fi

if [[ "$RUN_CRAWL" == true ]]; then
  CRAWL_ARGS=(
    uv run python -m homepage_crawler.main
    --log-dir /app/output/logs
    --update-diff-chars "$UPDATE_DIFF_CHARS"
    --concurrency "$CONCURRENCY"
  )
  if [[ -n "$CRAWL_LIMIT" ]]; then
    CRAWL_ARGS+=(--limit "$CRAWL_LIMIT")
  fi
  run_logged docker compose run --rm homepage-crawler "${CRAWL_ARGS[@]}"
fi

if [[ "$RUN_PIPELINE" == true ]]; then
  PIPELINE_ARGS=(uv run python -m crawler.pipline.cli run --source homepage)
  if [[ -n "$PIPELINE_LIMIT" ]]; then
    PIPELINE_ARGS+=(--limit "$PIPELINE_LIMIT")
  fi
  run_logged docker compose run --rm pipeline "${PIPELINE_ARGS[@]}"
fi

log "====== homepage server run completed ======"
log "log_file=$LOG_FILE"
