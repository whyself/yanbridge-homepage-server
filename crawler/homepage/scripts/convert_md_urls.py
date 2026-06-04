import argparse
import json
import re
from pathlib import Path


URL_RE = re.compile(r"^\s*-\s+(https?://\S+)\s*$")
NAME_RE = re.compile(r"^\s*-\s+(.+?)\s*$")
URL_LIST_RE = re.compile(r"^(?P<school>.+?)(?:_clean)?_(?P<source_type>faculty|lab)_urls\.md$")
UNIVERSITY_NAMES = {
    "fdu": "复旦大学",
    "fudan_university": "复旦大学",
    "nju": "南京大学",
    "nanjing_university": "南京大学",
    "pku": "北京大学",
    "peking_university": "北京大学",
    "sjtu": "上海交通大学",
    "shanghai_jiao_tong_university": "上海交通大学",
    "thu": "清华大学",
    "tsinghua_university": "清华大学",
    "ustc": "中国科学技术大学",
    "university_of_science_and_technology_of_china": "中国科学技术大学",
    "zju": "浙江大学",
    "zhejiang_university": "浙江大学",
}
SCHOOL_SLUG_ALIASES = {
    "fudan_university": "fdu",
    "nanjing_university": "nju",
    "peking_university": "pku",
    "shanghai_jiao_tong_university": "sjtu",
    "tsinghua_university": "thu",
    "university_of_science_and_technology_of_china": "ustc",
    "zhejiang_university": "zju",
}


def slug(value: str) -> str:
    value = re.sub(r"https?://", "", value.lower())
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", value)
    return value.strip("_")[:48]


def convert(
    input_path: Path,
    output_path: Path,
    batch: str,
    university: str,
    source_type: str,
    id_prefix: str,
    append: bool,
) -> int:
    rows = []
    current_name = ""
    counters: dict[str, int] = {}

    for line in input_path.read_text(encoding="utf-8").splitlines():
        url_match = URL_RE.match(line)
        if url_match and current_name:
            url = url_match.group(1)
            base_id = f"{id_prefix}_{slug(current_name)}"
            counters[base_id] = counters.get(base_id, 0) + 1
            rows.append({
                "id": f"{base_id}_{counters[base_id]:03d}",
                "batch": batch,
                "university": university,
                "source_type": source_type,
                "name": current_name,
                "url": url,
                "status": "active",
            })
            continue

        name_match = NAME_RE.match(line)
        if name_match and not URL_RE.match(line):
            current_name = name_match.group(1).strip()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append else "w"
    with output_path.open(mode, encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} rows to {output_path}")
    return len(rows)


def convert_all(input_dir: Path, output_dir: Path, batch_suffix: str) -> None:
    inputs = sorted(input_dir.glob("*_clean_*_urls.md"))
    if not inputs:
        inputs = sorted(input_dir.glob("*_urls.md"))
    if not inputs:
        raise FileNotFoundError(f"No URL markdown files found in {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    for stale_output in output_dir.glob("*.jsonl"):
        stale_output.unlink()

    total = 0
    for input_path in inputs:
        match = URL_LIST_RE.match(input_path.name)
        if not match:
            print(f"skip {input_path}: filename does not match *_faculty_urls.md or *_lab_urls.md")
            continue

        school_slug = match.group("school")
        school_slug = SCHOOL_SLUG_ALIASES.get(school_slug, school_slug)
        source_type = match.group("source_type")
        university = UNIVERSITY_NAMES.get(school_slug, school_slug.replace("_", " ").title())
        output_path = output_dir / f"{school_slug}.jsonl"
        total += convert(
            input_path=input_path,
            output_path=output_path,
            batch=f"{school_slug}_{batch_suffix}",
            university=university,
            source_type=source_type,
            id_prefix=f"{school_slug}_{source_type}",
            append=output_path.exists(),
        )
    print(f"wrote {total} rows from {len(inputs)} markdown files")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path, nargs="?")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--batch")
    parser.add_argument("--university", default="南京大学")
    parser.add_argument("--source-type", choices=["faculty", "lab"])
    parser.add_argument("--id-prefix")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--input-dir", type=Path, default=Path("docs"))
    parser.add_argument("--output-dir", type=Path, default=Path("config"))
    parser.add_argument("--batch-suffix", default="202605")
    args = parser.parse_args()
    if args.all:
        convert_all(args.input_dir, args.output_dir, args.batch_suffix)
        return

    missing = [
        name
        for name, value in {
            "input": args.input,
            "output": args.output,
            "--batch": args.batch,
            "--source-type": args.source_type,
            "--id-prefix": args.id_prefix,
        }.items()
        if value is None
    ]
    if missing:
        parser.error(f"missing required arguments for single-file mode: {', '.join(missing)}")

    convert(args.input, args.output, args.batch, args.university, args.source_type, args.id_prefix, args.append)


if __name__ == "__main__":
    main()
