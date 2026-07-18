#!/usr/bin/env python3
"""Interactive terminal chat for the standalone homepage agent.

Usage:
  python scripts/chat_homepage_agent.py
  python scripts/chat_homepage_agent.py --database-url postgresql://...

Commands inside the chat:
  /help       Show commands
  /reset      Clear agent conversation memory
  /tools      Show available tools
  /quit       Exit
"""

from __future__ import annotations

import argparse
import json
import readline  # noqa: F401  # Enables input history on most terminals.
import sys
import textwrap
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from homepage_agent import AgentConfig, AgentTools, build_agent  # noqa: E402
from homepage_agent.config import load_env  # noqa: E402
from homepage_agent.tools import tool_schemas  # noqa: E402


class Colors:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def paint(self, text: str, code: str) -> str:
        if not self.enabled:
            return text
        return f"\033[{code}m{text}\033[0m"

    def cyan(self, text: str) -> str:
        return self.paint(text, "36")

    def green(self, text: str) -> str:
        return self.paint(text, "32")

    def yellow(self, text: str) -> str:
        return self.paint(text, "33")

    def red(self, text: str) -> str:
        return self.paint(text, "31")

    def dim(self, text: str) -> str:
        return self.paint(text, "2")


def main() -> None:
    parser = argparse.ArgumentParser(description="Talk with the standalone homepage teacher agent.")
    parser.add_argument("--env-file", default=None, help="Optional .env path. Defaults to yanbridge-homepage-server/.env")
    parser.add_argument("--database-url", default=None, help="Override DATABASE_URL")
    parser.add_argument("--crw-api-url", default=None, help="Override CRW_API_URL")
    parser.add_argument("--model", default=None, help="Override AGENT_MODEL/DEEPSEEK_MODEL")
    parser.add_argument("--max-steps", type=int, default=8, help="Max tool-call rounds per message")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors")
    args = parser.parse_args()

    load_env(args.env_file)
    config = AgentConfig()
    if args.database_url:
        config.database_url = args.database_url
    if args.crw_api_url:
        config.crw_api_url = args.crw_api_url.rstrip("/")
    if args.model:
        config.agent_model = args.model

    colors = Colors(enabled=(not args.no_color and sys.stdout.isatty()))
    tools = AgentTools(config)
    agent = build_agent(config=config, tools=tools)
    session = agent.start_session(on_tool_call=lambda name, call_args, result: print_tool_call(colors, name, call_args, result))

    print_banner(colors, config)
    try:
        while True:
            try:
                user_text = input(colors.green("you> ")).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not user_text:
                continue
            if user_text in {"/quit", "/exit", "q", "quit", "exit"}:
                break
            if user_text == "/help":
                print_help(colors)
                continue
            if user_text == "/reset":
                session.reset()
                print(colors.yellow("Conversation memory reset."))
                continue
            if user_text == "/tools":
                print_json(tool_schemas())
                continue

            try:
                answer = session.ask(user_text, max_steps=args.max_steps)
            except Exception as exc:
                print(colors.red(f"error> {type(exc).__name__}: {exc}"))
                continue

            print_wrapped(colors.cyan("agent> "), answer)
    finally:
        agent.close()


def print_banner(colors: Colors, config: AgentConfig) -> None:
    print(colors.cyan("Yanbridge Homepage Agent TUI"))
    print(colors.dim(f"model: {config.agent_model}"))
    print(colors.dim(f"crw:   {config.crw_api_url}"))
    print(colors.dim("type /help for commands, /quit to exit"))
    print()


def print_help(colors: Colors) -> None:
    print(colors.cyan("Commands:"))
    print("  /help   show this help")
    print("  /reset  clear conversation memory")
    print("  /tools  print available agent tool schemas")
    print("  /quit   exit")
    print()
    print(colors.cyan("Example:"))
    print("  Find whether 南京大学 ISET has teachers recruiting students. Verify with URLs and update post only if evidence is clear.")


def print_tool_call(colors: Colors, name: str, call_args: dict[str, Any], result: dict[str, Any]) -> None:
    print(colors.yellow(f"tool> {name}"))
    print(colors.dim(f"args: {compact_json(call_args)}"))
    print(colors.dim(f"result: {summarize_result(result)}"))


def summarize_result(result: dict[str, Any]) -> str:
    if "results" in result and isinstance(result["results"], list):
        return f"{len(result['results'])} search results"
    if "matches" in result and isinstance(result["matches"], list):
        return f"{len(result['matches'])} post matches"
    if "post" in result:
        post = result.get("post") or {}
        return f"post {post.get('id') or post.get('dedupe_key') or 'updated'}"
    text = compact_json(result)
    return text[:240] + ("..." if len(text) > 240 else "")


def compact_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def print_json(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def print_wrapped(prefix: str, text: str) -> None:
    width = max(60, min(100, _terminal_width()))
    lines = text.splitlines() or [""]
    first = True
    for line in lines:
        wrapped = textwrap.wrap(line, width=width - len(strip_ansi(prefix))) or [""]
        for part in wrapped:
            if first:
                print(prefix + part)
                first = False
            else:
                print(" " * len(strip_ansi(prefix)) + part)


def _terminal_width() -> int:
    try:
        return __import__("shutil").get_terminal_size((100, 20)).columns
    except Exception:
        return 100


def strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\033\[[0-9;]*m", "", text)


if __name__ == "__main__":
    main()

