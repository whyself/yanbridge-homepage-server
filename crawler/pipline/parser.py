"""流水线主编排器 — PipelineRunner。

连接 RawLoader → Adapter → OCR → LLM → Writer。
"""

from __future__ import annotations

from .adapter import get_adapter
from .adapter.base import AbstractSourceAdapter
from .config import PipelineConfig
from .llm import LLMClient
from .models import RawRecord, SourceType
from .ocr import OCRExtractor
from .reader import HomepageRawLoader, RawLoader, XhsRawLoader
from .writer import PostWriter


class PipelineRunner:
    """流水线编排器。

    Usage:
        runner = PipelineRunner(config, source_type="xiaohongshu")
        runner.run()
    """

    def __init__(self, config: PipelineConfig, source_type: str, enable_ocr: bool = True):
        self.config = config
        self.source_type = source_type
        self.enable_ocr = enable_ocr

        # 组件
        self.adapter: AbstractSourceAdapter = get_adapter(source_type)
        self.raw_loader: RawLoader = self._create_raw_loader()
        self.writer = PostWriter(config)
        self.llm_client = LLMClient(
            api_key=config.deepseek_api_key,
            api_url=config.deepseek_api_url,
            model=config.deepseek_model,
            max_retries=config.max_retries,
            retry_delay=config.retry_delay,
            request_interval=config.request_interval,
        )
        self.ocr_extractor: OCRExtractor | None = None
        if self.enable_ocr:
            self.ocr_extractor = OCRExtractor(config.media_root_path)

        # 统计
        self.stats: dict[str, int] = {
            "total": 0, "kept": 0, "rewritten": 0, "discarded": 0, "failed": 0,
        }

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    def run(
        self,
        dry_run: bool = False,
        limit: int = 0,
    ) -> dict[str, int]:
        """执行流水线。

        Args:
            dry_run: 仅预览，不实际写入。
            limit: 限制处理条数，0 表示不限制。

        Returns:
            统计 dict。
        """
        # Resume: 获取已处理的 dedupe_key
        dedupe_prefix = self._get_dedupe_prefix()
        processed = self.writer.get_processed_keys(prefix=dedupe_prefix)
        if processed:
            print(f"已处理 {len(processed)} 条，跳过")

        total = self.raw_loader.count_unprocessed(processed)
        print(f"待处理 {total} 条")

        if dry_run:
            print("[DRY RUN] 预览前 3 条:")
            records = self.raw_loader.fetch_unprocessed(processed)
            for i, rec in enumerate(records):
                if i >= 3:
                    break
                extracted = self.adapter.extract(rec)
                print(f"  {self.adapter.build_dedupe_key(extracted)}"
                      f" — {extracted.get('title', '')[:40]}")
                self.stats["total"] += 1
            print(f"... 共 {total} 条 (dry-run, 不实际处理)")
            return self.stats

        # 正式处理
        records = self.raw_loader.fetch_unprocessed(processed)
        for i, rec in enumerate(records, 1):
            if limit and i > limit:
                break
            self._process_one(i, total, rec)

        # 打印汇总
        print(f"\n完成: 保留 {self.stats['kept']}"
              f" (重写 {self.stats['rewritten']})"
              f", 丢弃 {self.stats['discarded']}"
              f", 失败 {self.stats['failed']}")
        return self.stats

    def _process_one(self, idx: int, total: int, rec: RawRecord) -> None:
        """处理单条记录。"""
        self.stats["total"] += 1
        extracted = self.adapter.extract(rec)
        dedupe_key = self.adapter.build_dedupe_key(extracted)
        title = extracted.get("title", "") or extracted.get("page_title", "") or "?"

        print(f"[{idx}/{total}] {dedupe_key} — {str(title)[:40]}... ", end="", flush=True)

        # 1. OCR (默认开启)
        if self.adapter.needs_ocr(extracted) and self.ocr_extractor:
            try:
                ocr_text = self.ocr_extractor.extract_text(extracted)
                if ocr_text:
                    # 将 OCR 文字追加到 description / text
                    key = "description" if "description" in extracted else "text"
                    extracted[key] = (extracted.get(key, "") or "") + "\n\n[OCR]\n" + ocr_text
                    print("[OCR] ", end="", flush=True)
            except Exception as e:
                print(f"[OCR错误:{e}] ", end="", flush=True)

        # 2. LLM
        sys_prompt, user_prompt = self.adapter.build_llm_prompt(extracted)
        llm_result = self.llm_client.call(sys_prompt, user_prompt)

        if llm_result is None:
            print("SKIP (API失败)")
            self.stats["failed"] += 1
            return

        # 3. 分类处理
        action = llm_result.action
        if action == "irrelevant":
            print("DISCARD")
            self.stats["discarded"] += 1
            self.writer.mark_discarded(
                dedupe_key=dedupe_key,
                source_type=str(self.adapter.source_type),
                title=str(title),
                source_url=extracted.get("note_url") or extracted.get("requested_url") or extracted.get("final_url"),
                reason=action,
                metadata={
                    "llm_result": llm_result.raw_response,
                    "raw_source_type": str(rec.source_type),
                },
            )
            self._mark_raw_processed(rec, extracted)
            return
        elif action == "rewrite":
            self.stats["rewritten"] += 1
            print(f"REWRITE → {llm_result.title[:30]}")
        else:
            print(f"KEEP")

        self.stats["kept"] += 1

        # 4. Content 改写 (主 LLM 调用已输出 content 字段，此处为降级兼容)
        rewritten_content: str | None = None
        prompt = self.adapter.build_content_prompt(extracted)
        if prompt:
            text = self.llm_client.rewrite_content(*prompt)
            if text:
                rewritten_content = text

        # 5. 生成 Post 并写入
        post = self.adapter.to_post(rec, extracted, llm_result, rewritten_content)
        self.writer.upsert(post)
        self._mark_raw_processed(rec, extracted)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _create_raw_loader(self) -> RawLoader:
        if self.source_type in ("xiaohongshu",):
            return XhsRawLoader(self.config)
        elif self.source_type in ("personal_website", "homepage"):
            return HomepageRawLoader(self.config)
        else:
            raise ValueError(f"不支持的 source_type: {self.source_type}")

    def _get_dedupe_prefix(self) -> str:
        if self.source_type in ("xiaohongshu",):
            return "xhs:note:"
        elif self.source_type in ("personal_website", "homepage"):
            return "website:"
        return ""

    def _mark_raw_processed(self, rec: RawRecord, extracted: dict) -> None:
        if rec.source_type != SourceType.PERSONAL_WEBSITE:
            return
        self.writer.mark_homepage_raw_processed(
            extracted.get("source_id", ""),
            extracted.get("content_hash", ""),
        )

    def close(self) -> None:
        self.raw_loader.close()
        self.writer.close()
