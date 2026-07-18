import argparse
from pathlib import Path

from .config import DEFAULT_BATCH_DIR
from .source_store import import_url_items_to_pg
from .url_loader import load_url_items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import homepage JSONL URL sources into PostgreSQL.")
    parser.add_argument("--url-list", type=Path, default=None)
    parser.add_argument("--batch-dir", type=Path, default=DEFAULT_BATCH_DIR)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.url_list:
        url_lists = [args.url_list]
    else:
        url_lists = sorted(args.batch_dir.glob("*.jsonl"))
    if not url_lists:
        raise FileNotFoundError(f"No URL list files found in {args.batch_dir}")

    items = []
    for url_list in url_lists:
        items.extend(load_url_items(url_list))
    if args.limit is not None:
        items = items[: args.limit]

    imported = import_url_items_to_pg(items)
    print(f"homepage_sources_imported={imported}")


if __name__ == "__main__":
    main()
