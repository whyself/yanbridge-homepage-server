import difflib
import re
from dataclasses import dataclass
from typing import Mapping


DEFAULT_DIFF_CHAR_THRESHOLD = 10
MAX_DIFF_CHARS = 20000


@dataclass(frozen=True)
class UpdateDecision:
    source_id: str
    status: str
    diff_chars: int | None = None


@dataclass(frozen=True)
class UpdateSummary:
    new: int = 0
    changed: int = 0
    low_diff: int = 0
    unchanged: int = 0
    failed: int = 0

    @property
    def effective_updates(self) -> int:
        return self.new + self.changed


def summarize_updates(
    old_rows: Mapping[str, Mapping],
    new_rows: list[dict],
    diff_char_threshold: int = DEFAULT_DIFF_CHAR_THRESHOLD,
) -> UpdateSummary:
    return summarize_decisions(decide_updates(old_rows, new_rows, diff_char_threshold))


def summarize_decisions(decisions: list[UpdateDecision]) -> UpdateSummary:
    counts = {
        "new": 0,
        "changed": 0,
        "low_diff": 0,
        "unchanged": 0,
        "failed": 0,
    }

    for decision in decisions:
        counts[decision.status] += 1

    return UpdateSummary(**counts)


def decide_updates(
    old_rows: Mapping[str, Mapping],
    new_rows: list[dict],
    diff_char_threshold: int = DEFAULT_DIFF_CHAR_THRESHOLD,
) -> list[UpdateDecision]:
    decisions = []
    for row in new_rows:
        source_id = str(row.get("source_id") or "")
        if row.get("status") != "success":
            decisions.append(UpdateDecision(source_id=source_id, status="failed"))
            continue

        old_row = old_rows.get(source_id) if source_id else None
        if not old_row or old_row.get("status") != "success":
            decisions.append(UpdateDecision(source_id=source_id, status="new", diff_chars=None))
            continue

        old_hash = old_row.get("content_hash") or ""
        new_hash = row.get("content_hash") or ""
        if old_hash and new_hash and old_hash == new_hash:
            decisions.append(UpdateDecision(source_id=source_id, status="unchanged", diff_chars=0))
            continue

        diff_chars = content_diff_chars(old_row.get("text") or "", row.get("text") or "")
        status = "changed" if diff_chars >= diff_char_threshold else "low_diff"
        decisions.append(UpdateDecision(source_id=source_id, status=status, diff_chars=diff_chars))
    return decisions


def content_diff_chars(old_text: str, new_text: str) -> int:
    old_normalized = _normalize_text(old_text)[:MAX_DIFF_CHARS]
    new_normalized = _normalize_text(new_text)[:MAX_DIFF_CHARS]
    if not old_normalized and not new_normalized:
        return 0
    if not old_normalized or not new_normalized:
        return max(len(old_normalized), len(new_normalized))

    matcher = difflib.SequenceMatcher(None, old_normalized, new_normalized)
    changed_chars = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            changed_chars += max(i2 - i1, j2 - j1)
    return changed_chars


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()
