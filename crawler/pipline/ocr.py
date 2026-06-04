"""OCR 文字提取工具。

从 xhs_note_images 的 storage_key 通过 MEDIA_ROOT 定位本地 WebP 图片，
使用 RapidOCR (ONNX Runtime) 提取文字。
"""

from __future__ import annotations

from pathlib import Path


class OCRExtractor:
    """从本地图片文件中提取文字。

    图片通过 MEDIA_ROOT / storage_key 定位，
    即 crawler/xhs-lyc 已下载并压缩为 WebP 的本地文件。
    """

    def __init__(self, media_root: Path | str):
        self.media_root = Path(media_root)
        self._ocr = None

    @property
    def ocr(self):
        """延迟初始化 RapidOCR。"""
        if self._ocr is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                self._ocr = RapidOCR()
            except ImportError:
                raise ImportError(
                    "RapidOCR 未安装。请运行: pip install rapidocr-onnxruntime"
                )
        return self._ocr

    # ------------------------------------------------------------------
    # 公共接口
    # ------------------------------------------------------------------

    def extract_text(self, extracted: dict) -> str:
        """从 extracted dict 中提取所有图片的文字。

        extracted 应包含 "images" 列表，每个元素含 storage_key。
        返回所有图片拼接的文字。
        """
        images = extracted.get("images") or []
        if not images:
            return ""

        texts: list[str] = []
        for img_info in images:
            storage_key = img_info.get("storage_key", "")
            if not storage_key:
                continue
            text = self.extract_from_file(storage_key)
            if text:
                texts.append(text)

        return "\n".join(texts)

    def extract_from_file(self, storage_key: str) -> str:
        """从单个 storage_key 提取文字。"""
        image_path = self._resolve(storage_key)
        if not image_path.exists():
            print(f"[OCR:文件不存在] {image_path}")
            return ""

        try:
            # RapidOCR()(img_path) → (result, elapse)
            # result: list of [bbox, text, confidence] or None
            result, _ = self.ocr(str(image_path))
            if not result:
                return ""
            lines = [item[1] for item in result if item[1].strip()]
            return "\n".join(lines)
        except Exception as e:
            print(f"[OCR:识别失败] {image_path}: {e}")
            return ""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _resolve(self, storage_key: str) -> Path:
        """安全解析 storage_key 为本地绝对路径。"""
        media_root = self.media_root.resolve()
        image_path = (media_root / storage_key).resolve()
        if not str(image_path).startswith(str(media_root)):
            raise ValueError(f"storage_key 试图越界: {storage_key}")
        return image_path
