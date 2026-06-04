from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_BATCH_DIR = BASE_DIR / "config"
DEFAULT_LOG_DIR = BASE_DIR / "output" / "logs"

DEFAULT_TIMEOUT_MS = 60000
DEFAULT_CONCURRENCY = 2
