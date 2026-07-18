import json
from pathlib import Path

from .models import UrlItem


def load_url_items(path: Path) -> list[UrlItem]:
    items: list[UrlItem] = []
    with path.open("r", encoding="utf-8") as file:
        for line_no, line in enumerate(file, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                item = UrlItem.from_dict(json.loads(line))
            except Exception as exc:
                raise ValueError(f"Invalid URL item at {path}:{line_no}: {exc}") from exc
            if item.status == "active":
                items.append(item)
    return items
