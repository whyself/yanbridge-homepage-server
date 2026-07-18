#!/usr/bin/env python3
"""Test the standalone homepage agent library.

Examples:
  python scripts/test_homepage_agent.py tools
  python scripts/test_homepage_agent.py search "南京大学 ISET 教师 招生"
  python scripts/test_homepage_agent.py scrape https://example.edu/profile
  python scripts/test_homepage_agent.py find --teacher-name 张三
  python scripts/test_homepage_agent.py update --write --title "测试" --teacher-name-cn 张三 --url https://example.edu
  python scripts/test_homepage_agent.py agent "Find NJU ISET teacher recruitment info and update the post if verified."
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from homepage_agent import AgentConfig, AgentTools, build_agent  # noqa: E402
from homepage_agent.config import load_env  # noqa: E402
from homepage_agent.tools import tool_schemas  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Test standalone homepage agent abilities.")
    parser.add_argument("--env-file", default=None, help="Optional .env path. Defaults to yanbridge-homepage-server/.env")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL")
    parser.add_argument("--crw-api-url", default=None, help="Override CRW_API_URL")
    parser.add_argument("--model", default=None, help="Override AGENT_MODEL/DEEPSEEK_MODEL")

    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tools", help="Print available tool schemas")

    p = sub.add_parser("search", help="Test CRW search")
    p.add_argument("query")
    p.add_argument("--limit", type=int, default=5)

    p = sub.add_parser("scrape", help="Test CRW scrape")
    p.add_argument("url")

    p = sub.add_parser("find", help="Test DB find_post")
    p.add_argument("--dedupe-key", default="")
    p.add_argument("--source-url", default="")
    p.add_argument("--university-name", default="")
    p.add_argument("--school-name", default="")
    p.add_argument("--teacher-name", default="")
    p.add_argument("--keyword", default="")
    p.add_argument("--limit", type=int, default=10)

    p = sub.add_parser("update", help="Test DB update_post; requires --write")
    p.add_argument("--write", action="store_true", help="Actually write to posts")
    p.add_argument("--title", required=True)
    p.add_argument("--content", default="")
    p.add_argument("--summary", default="")
    p.add_argument("--university-name", default="")
    p.add_argument("--school-name", default="")
    p.add_argument("--source-url", "--url", dest="source_url", default="")
    p.add_argument("--dedupe-key", default="")
    p.add_argument("--teacher-name-cn", default="")
    p.add_argument("--teacher-name-en", default="")
    p.add_argument("--evidence", action="append", default=[])

    p = sub.add_parser("agent", help="Run the DeepSeek tool-calling agent")
    p.add_argument("task")
    p.add_argument("--max-steps", type=int, default=8)

    args = parser.parse_args()
    load_env(args.env_file)
    config = AgentConfig()
    if args.database_url:
        config.database_url = args.database_url
    if args.crw_api_url:
        config.crw_api_url = args.crw_api_url.rstrip("/")
    if args.model:
        config.agent_model = args.model

    if args.cmd == "tools":
        print_json(tool_schemas())
        return

    tools = AgentTools(config)
    try:
        if args.cmd == "search":
            print_json(tools.crw_search(args.query, args.limit))
        elif args.cmd == "scrape":
            result = tools.crw_scrape(args.url)
            result["markdown"] = result["markdown"][:1200]
            result["text"] = result["text"][:1200]
            print_json(result)
        elif args.cmd == "find":
            print_json(
                tools.find_post(
                    dedupe_key=args.dedupe_key,
                    source_url=args.source_url,
                    university_name=args.university_name,
                    school_name=args.school_name,
                    teacher_name=args.teacher_name,
                    keyword=args.keyword,
                    limit=args.limit,
                )
            )
        elif args.cmd == "update":
            draft = {
                "title": args.title,
                "content": args.content,
                "summary": args.summary,
                "university_name": args.university_name,
                "school_name": args.school_name,
                "source_url": args.source_url,
                "dedupe_key": args.dedupe_key,
                "teacher_name_cn": args.teacher_name_cn,
                "teacher_name_en": args.teacher_name_en,
                "evidence": args.evidence,
            }
            if not args.write:
                print("Dry run. Add --write to update posts.")
                print_json(draft)
            else:
                print_json(tools.update_post(draft))
        elif args.cmd == "agent":
            agent = build_agent(config=config, tools=tools)
            print(agent.run(args.task, max_steps=args.max_steps))
    finally:
        tools.close()


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

