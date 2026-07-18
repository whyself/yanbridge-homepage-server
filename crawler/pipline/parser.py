"""流水线主编排器 — PipelineRunner。

连接 RawLoader → Adapter → OCR → LLM → Writer。
"""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
import json

from .adapter import get_adapter
from .adapter.base import AbstractSourceAdapter
from .config import PipelineConfig
from .llm import LLMClient
from .models import LLMResult, Post, PostCategory, RawRecord, SourceType
from .ocr import OCRExtractor
from .reader import HomepageRawLoader, RawLoader, XhsRawLoader
from .writer import PostWriter


@dataclass
class PipelineProcessResult:
    idx: int
    total: int
    rec: RawRecord
    extracted: dict
    dedupe_key: str
    title: str
    action: str | None = None
    llm_result: LLMResult | None = None
    post: Post | None = None
    error: str | None = None


def _build_llm_client(config: PipelineConfig) -> LLMClient:
    return LLMClient(
        api_key=config.deepseek_api_key,
        api_url=config.deepseek_api_url,
        model=config.deepseek_model,
        max_retries=config.max_retries,
        retry_delay=config.retry_delay,
        request_interval=config.request_interval,
    )


def _process_record_core(
    adapter: AbstractSourceAdapter,
    llm_client: LLMClient,
    ocr_extractor: OCRExtractor | None,
    rec: RawRecord,
    idx: int,
    total: int,
) -> PipelineProcessResult:
    extracted = adapter.extract(rec)
    dedupe_key = adapter.build_dedupe_key(extracted)
    title = extracted.get("title", "") or extracted.get("page_title", "") or "?"

    if adapter.needs_ocr(extracted) and ocr_extractor:
        try:
            ocr_text = ocr_extractor.extract_text(extracted)
            if ocr_text:
                key = "description" if "description" in extracted else "text"
                extracted[key] = (extracted.get(key, "") or "") + "\n\n[OCR]\n" + ocr_text
        except Exception as exc:
            return PipelineProcessResult(idx, total, rec, extracted, dedupe_key, str(title), error=f"OCR错误:{exc}")

    sys_prompt, user_prompt = adapter.build_llm_prompt(extracted)
    llm_result = llm_client.call(sys_prompt, user_prompt)
    if llm_result is None:
        return PipelineProcessResult(idx, total, rec, extracted, dedupe_key, str(title), error="API失败")

    action = llm_result.action
    post: Post | None = None
    if action != "irrelevant":
        rewritten_content: str | None = None
        prompt = adapter.build_content_prompt(extracted)
        if prompt:
            text = llm_client.rewrite_content(*prompt)
            if text:
                rewritten_content = text
        post = adapter.to_post(rec, extracted, llm_result, rewritten_content)

    return PipelineProcessResult(
        idx=idx,
        total=total,
        rec=rec,
        extracted=extracted,
        dedupe_key=dedupe_key,
        title=str(title),
        action=action,
        llm_result=llm_result,
        post=post,
    )


def _process_record_worker(
    config: PipelineConfig,
    source_type: str,
    enable_ocr: bool,
    rec: RawRecord,
    idx: int,
    total: int,
) -> PipelineProcessResult:
    adapter = get_adapter(source_type)
    ocr_extractor = OCRExtractor(config.media_root_path) if enable_ocr else None
    return _process_record_core(adapter, _build_llm_client(config), ocr_extractor, rec, idx, total)


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
        self.llm_client = _build_llm_client(config)
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
        workers: int = 1,
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
        pending_items = []
        for i, rec in enumerate(self.raw_loader.fetch_unprocessed(processed), 1):
            if limit and i > limit:
                break
            pending_items.append((i, rec))

        process_total = len(pending_items)

        # Group pending items by content_hash to optimize and deduplicate LLM calls
        hash_to_items = {}
        no_hash_items = []
        for idx, rec in pending_items:
            extracted = self.adapter.extract(rec)
            h = extracted.get("content_hash")
            if h:
                hash_to_items.setdefault(h, []).append((idx, rec, extracted))
            else:
                no_hash_items.append((idx, rec, extracted))

        # Bulk check database cache by content hashes
        cached_results = {}
        if hash_to_items:
            cached_results = self.writer.get_cached_results_by_hashes(hash_to_items.keys())

        # Process cached items in main thread (no worker/LLM required)
        for h in list(hash_to_items.keys()):
            if h in cached_results:
                cached_res = cached_results[h]
                action = cached_res["action"]
                
                # Reconstruct LLMResult
                if action == "keep":
                    meta_dict = cached_res.get("metadata")
                    if isinstance(meta_dict, str):
                        meta_dict = json.loads(meta_dict)
                    elif meta_dict is None:
                        meta_dict = {}

                    llm_result = LLMResult(
                        action="keep",
                        title=cached_res["title"],
                        category=cached_res["category"],
                        university_name=cached_res["university_name"],
                        school_name=cached_res["school_name"],
                        major_name=cached_res["major_name"],
                        summary=cached_res["summary"],
                        content=cached_res["content"],
                        raw_response=meta_dict.get("llm_result") or {},
                    )
                else:
                    llm_result = LLMResult(
                        action="irrelevant",
                        title="",
                        raw_response=cached_res.get("llm_result_raw") or {},
                    )

                # Commit for all duplicate items sharing this hash
                for idx, rec, extracted in hash_to_items[h]:
                    post = None
                    if action == "keep":
                        post = self.adapter.to_post(rec, extracted, llm_result)
                    
                    result = PipelineProcessResult(
                        idx=idx,
                        total=process_total,
                        rec=rec,
                        extracted=extracted,
                        dedupe_key=self.adapter.build_dedupe_key(extracted),
                        title=post.title if post else (extracted.get("page_title") or ""),
                        action=action,
                        llm_result=llm_result,
                        post=post,
                    )
                    print("[CACHED] ", end="")
                    self._commit_result(result)

                # Remove from hash_to_items so we don't process it in workers
                del hash_to_items[h]

        # Prepare items to submit to workers (only representative for each unique content hash)
        to_submit = []
        rep_idx_to_duplicates = {}
        for h, items in hash_to_items.items():
            rep_idx, rep_rec, rep_extracted = items[0]
            to_submit.append((rep_idx, rep_rec))
            if len(items) > 1:
                rep_idx_to_duplicates[rep_idx] = items[1:]

        for idx, rec, extracted in no_hash_items:
            to_submit.append((idx, rec))

        # Run workers
        if to_submit:
            if workers <= 1:
                for idx, rec in to_submit:
                    result = _process_record_core(
                        self.adapter,
                        self.llm_client,
                        self.ocr_extractor,
                        rec,
                        idx,
                        process_total,
                    )
                    self._commit_result(result)
                    if idx in rep_idx_to_duplicates:
                        self._replicate_result(result, rep_idx_to_duplicates[idx], process_total)
            else:
                print(f"使用 {workers} 个 worker 处理；LLM 请求速率会随 worker 数放大")
                with ProcessPoolExecutor(max_workers=workers) as executor:
                    futures = {
                        executor.submit(
                            _process_record_worker,
                            self.config,
                            self.source_type,
                            self.enable_ocr,
                            rec,
                            idx,
                            process_total,
                        ): idx
                        for idx, rec in to_submit
                    }
                    for future in as_completed(futures):
                        idx = futures[future]
                        try:
                            result = future.result()
                            self._commit_result(result)
                            if idx in rep_idx_to_duplicates:
                                self._replicate_result(result, rep_idx_to_duplicates[idx], process_total)
                        except Exception as exc:
                            print(f"[worker错误] {type(exc).__name__}: {exc}")
                            self.stats["failed"] += 1
                            if idx in rep_idx_to_duplicates:
                                for dup_idx, _, _ in rep_idx_to_duplicates[idx]:
                                    print(f"[{dup_idx}/{process_total}] SKIP (代表记录处理失败)")
                                    self.stats["failed"] += 1

        # 打印汇总
        print(f"\n完成: 保留 {self.stats['kept']}"
              f" (重写 {self.stats['rewritten']})"
              f", 丢弃 {self.stats['discarded']}"
              f", 失败 {self.stats['failed']}")
        return self.stats

    def _process_one(self, idx: int, total: int, rec: RawRecord) -> None:
        """处理单条记录。"""
        result = _process_record_core(
            self.adapter,
            self.llm_client,
            self.ocr_extractor,
            rec,
            idx,
            total,
        )
        self._commit_result(result)

    def _replicate_result(self, rep_result: PipelineProcessResult, duplicates: list[tuple[int, RawRecord, dict]], process_total: int) -> None:
        """Replicate a representative result to duplicate items."""
        if rep_result.error or rep_result.llm_result is None:
            for dup_idx, _, _ in duplicates:
                print(f"[{dup_idx}/{process_total}] SKIP (代表记录处理失败)")
                self.stats["failed"] += 1
            return

        action = rep_result.action or "keep"
        for dup_idx, dup_rec, dup_extracted in duplicates:
            post = None
            if action in ("keep", "rewrite"):
                post = self.adapter.to_post(dup_rec, dup_extracted, rep_result.llm_result)
            
            dup_result = PipelineProcessResult(
                idx=dup_idx,
                total=process_total,
                rec=dup_rec,
                extracted=dup_extracted,
                dedupe_key=self.adapter.build_dedupe_key(dup_extracted),
                title=post.title if post else (dup_extracted.get("page_title") or ""),
                action=action,
                llm_result=rep_result.llm_result,
                post=post,
            )
            print("[DUPLICATE] ", end="")
            self._commit_result(dup_result)

    def _commit_result(self, result: PipelineProcessResult) -> None:
        """Parent-process DB writes for a processed result."""
        self.stats["total"] += 1
        extracted = result.extracted
        rec = result.rec
        title = result.title

        print(f"[{result.idx}/{result.total}] {result.dedupe_key} — {str(title)[:40]}... ", end="", flush=True)

        if result.error or result.llm_result is None:
            print(f"SKIP ({result.error or '未知错误'})")
            self.stats["failed"] += 1
            return

        action = result.action or "keep"
        if action == "irrelevant":
            print("DISCARD")
            self.stats["discarded"] += 1
            self._sync_school_faculty_source(result)
            self.writer.mark_discarded(
                dedupe_key=result.dedupe_key,
                source_type=str(self.adapter.source_type),
                title=str(title),
                source_url=extracted.get("note_url") or extracted.get("requested_url") or extracted.get("final_url"),
                reason=action,
                metadata={
                    "llm_result": result.llm_result.raw_response,
                    "raw_source_type": str(rec.source_type),
                    "content_hash": extracted.get("content_hash"),
                },
            )
            self._mark_raw_processed(rec, extracted)
            return
        elif action == "rewrite":
            self.stats["rewritten"] += 1
            print(f"REWRITE → {result.llm_result.title[:30]}")
        else:
            print(f"KEEP")

        self.stats["kept"] += 1

        if result.post is None:
            print("SKIP (Post生成失败)")
            self.stats["failed"] += 1
            return
        self.writer.upsert(result.post)
        self._sync_school_faculty_source(result)
        self._mark_raw_processed(rec, extracted)

    def _sync_school_faculty_source(self, result: PipelineProcessResult) -> None:
        if result.rec.source_type != SourceType.PERSONAL_WEBSITE or result.llm_result is None:
            return
        self.writer.upsert_school_faculty_source(
            result.extracted,
            result.llm_result,
            post=result.post,
            raw_version_key=result.dedupe_key,
        )

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
