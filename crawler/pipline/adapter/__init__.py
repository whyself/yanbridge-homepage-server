"""适配器注册表。"""

from .base import AbstractSourceAdapter
from .xhs import XHSAdapter
from .homepage import HomepageAdapter

_ADAPTERS: dict[str, type[AbstractSourceAdapter]] = {}


def register_adapter(source_type: str, adapter_cls: type[AbstractSourceAdapter]) -> None:
    _ADAPTERS[source_type] = adapter_cls


def get_adapter(source_type: str) -> AbstractSourceAdapter:
    """根据 source_type 字符串获取适配器实例。"""
    cls = _ADAPTERS.get(source_type)
    if cls is None:
        raise ValueError(f"未知的 source_type: {source_type}，已注册: {list(_ADAPTERS)}")
    return cls()


# 自动注册
register_adapter("xiaohongshu", XHSAdapter)
register_adapter("personal_website", HomepageAdapter)
register_adapter("homepage", HomepageAdapter)  # alias
