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
import os
import sys


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
        stats = runner.run(dry_run=args.dry_run, limit=args.limit)
        if not args.dry_run:
            if stats["failed"] > 0:
                sys.exit(1)
    finally:
        runner.close()


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
    p_run.set_defaults(func=cmd_run)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
