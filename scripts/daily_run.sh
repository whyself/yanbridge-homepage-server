#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

RANDOM_DELAY=$((RANDOM % 301))
echo "[$(date)] 随机延迟 ${RANDOM_DELAY} 秒后开始 homepage 每日任务"
sleep "$RANDOM_DELAY"

exec scripts/run_once.sh
