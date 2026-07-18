from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class UrlItem:
    id: str
    batch: str
    university: str
    source_type: str
    name: str
    url: str
    status: str = "active"

    @classmethod
    def from_dict(cls, data: dict) -> "UrlItem":
        required = ("id", "batch", "university", "source_type", "name", "url")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"missing required fields: {', '.join(missing)}")
        if data["source_type"] not in {"faculty", "lab"}:
            raise ValueError("source_type must be faculty or lab")
        parsed = urlparse(data["url"])
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be http(s)")
        return cls(
            id=str(data["id"]),
            batch=str(data["batch"]),
            university=str(data["university"]),
            source_type=str(data["source_type"]),
            name=str(data["name"]),
            url=str(data["url"]),
            status=str(data.get("status", "active")),
        )
