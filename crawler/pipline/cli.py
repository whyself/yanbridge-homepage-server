#!/usr/bin/env python3
"""CLI 统一入口。

Usage:
    # 作为模块运行 (推荐)
    PYTHONPATH=/home/yama/repos/yanbridge python -m crawler.pipline.cli run --source xiaohongshu

    # 直接运行
    uv run python cli.py run --source xhs

    # Homepage 流水线从 PostgreSQL homepage_raw_page 读取
    uv run python cli.py run --source homepage

    # 选项
    uv run python cli.py run --source xhs --dry-run --limit 5
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path


SOURCE_ALIASES = {
    "xhs": "xiaohongshu",
    "xiaohongshu": "xiaohongshu",
    "homepage": "homepage",
    "website": "homepage",
    "personal_website": "homepage",
}


class PipelineArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        if "invalid choice" in message and "--source" in sys.argv:
            self.print_usage(sys.stderr)
            self.exit(
                2,
                f"{self.prog}: error: {message}\n"
                "提示: 运行流水线需要子命令 run，例如: uv run cli.py run --source xhs\n",
            )
        super().error(message)


def _normalize_source(source: str) -> str:
    try:
        return SOURCE_ALIASES[source]
    except KeyError as exc:
        choices = ", ".join(sorted(SOURCE_ALIASES))
        raise argparse.ArgumentTypeError(f"未知数据源: {source} (可选: {choices})") from exc


# 支持直接运行和模块导入两种方式
if __name__ == "__main__" and __package__ is None:
    # 直接运行时，把项目根目录加入 path 以便绝对导入
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.dirname(os.path.dirname(_here))  # yanbridge/
    if _root not in sys.path:
        sys.path.insert(0, _root)
    from crawler.pipline.config import PipelineConfig
    from crawler.pipline.parser import PipelineRunner
else:
    from .config import PipelineConfig
    from .parser import PipelineRunner


def cmd_run(args: argparse.Namespace) -> None:
    """执行流水线。"""
    source = args.source

    if not args.dry_run:
        api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        if not api_key:
            print("[错误] 请设置环境变量 DEEPSEEK_API_KEY")
            sys.exit(1)

    config = PipelineConfig()

    runner = PipelineRunner(config, source_type=source, enable_ocr=not args.no_ocr)
    try:
        stats = runner.run(dry_run=args.dry_run, limit=args.limit, workers=args.workers)
        if not args.dry_run:
            if stats["failed"] > 0:
                sys.exit(1)
    finally:
        runner.close()


def cmd_academic(args: argparse.Namespace) -> None:
    _load_homepage_server_env()
    model = args.model or os.environ.get("AGENT_MODEL", "") or "deepseek-v4-flash"
    if _uses_deepseek_model(model) and not os.environ.get("DEEPSEEK_API_KEY", ""):
        print("[错误] academic 会调用模型；使用 deepseek 模型时请设置环境变量 DEEPSEEK_API_KEY")
        sys.exit(1)

    if __package__:
        from .academic_runner import amain as academic_amain
    else:
        from crawler.pipline.academic_runner import amain as academic_amain

    # academic_runner owns its argparse for module usage. Rebuild sys.argv so the
    # same implementation serves both entry points without duplicating options.
    forwarded = [sys.argv[0]]
    for flag, value in (
        ("--limit", args.limit),
        ("--source-id", args.source_id),
        ("--max-text-chars", args.max_text_chars),
        ("--model", args.model),
        ("--workers", args.workers),
        ("--jsonl-output", args.jsonl_output),
    ):
        if value:
            forwarded.extend([flag, str(value)])
    if args.include_processed:
        forwarded.append("--include-processed")
    if args.dry_run:
        forwarded.append("--dry-run")
    old_argv = sys.argv
    try:
        sys.argv = forwarded
        asyncio.run(academic_amain())
    finally:
        sys.argv = old_argv


def main() -> None:
    parser = PipelineArgumentParser(
        description="Yanbridge 数据流水线 — 原始数据(DB) → 统一 Post 结构"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="运行流水线")
    p_run.add_argument(
        "--source", required=True,
        type=_normalize_source,
        metavar="{xhs,xiaohongshu,homepage,website,personal_website}",
        help="数据源",
    )

    p_run.add_argument(
        "--dry-run", action="store_true",
        help="for debug",
    )
    p_run.add_argument(
        "--limit", type=int, default=0,
        help="限制处理条数 (0=不限制)",
    )
    p_run.add_argument(
        "--no-ocr", action="store_true",
        help="跳过图片 OCR，只使用文本内容进入 LLM",
    )
    p_run.add_argument(
        "--workers", type=int, default=1,
        help="并行 worker 数；>1 时 worker 处理 LLM/OCR，父进程统一写库 (默认 1)",
    )
    p_run.set_defaults(func=cmd_run)

    p_academic = sub.add_parser("academic", help="Run Pydantic AI academic builder from homepage_raw_page")
    p_academic.add_argument("--limit", type=int, default=0, help="Limit raw rows. 0=all unprocessed.")
    p_academic.add_argument("--source-id", default="", help="Run a single source_id.")
    p_academic.add_argument("--include-processed", action="store_true", help="Do not skip existing agent_runs.")
    p_academic.add_argument("--dry-run", action="store_true", help="Run without writing academic tables.")
    p_academic.add_argument("--max-text-chars", type=int, default=8000)
    p_academic.add_argument("--model", default="", help="Override AGENT_MODEL.")
    p_academic.add_argument("--workers", type=int, default=1, help="Concurrent model extraction workers. Max 2500.")
    p_academic.add_argument("--jsonl-output", default="", help="Optional per-row JSONL output path.")
    p_academic.set_defaults(func=cmd_academic)

    args = parser.parse_args()
    args.func(args)


def _load_homepage_server_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


def _uses_deepseek_model(model: str) -> bool:
    return model.startswith("deepseek:") or model.startswith("deepseek-")


if __name__ == "__main__":
    main()
