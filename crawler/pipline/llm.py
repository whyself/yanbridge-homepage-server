"""通用 LLM 客户端，从 llm_process.py 提取并泛化。

支持自定义 system/user prompt，DeepSeek JSON Mode 输出，429 退避重试。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .models import LLMResult


class LLMClient:
    """DeepSeek Chat API 客户端。

    用法:
        client = LLMClient(api_key="sk-xxx")
        result = client.call(system_prompt="...", user_prompt="...")
    """

    def __init__(
        self,
        api_key: str,
        api_url: str = "https://api.deepseek.com/chat/completions",
        model: str = "deepseek-chat",
        max_retries: int = 3,
        retry_delay: float = 5.0,
        request_interval: float = 0.5,
    ):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.request_interval = request_interval
        self._last_call_time: float = 0.0

    def call(self, system_prompt: str, user_prompt: str) -> LLMResult | None:
        """调用 LLM（JSON Mode），返回结构化分类结果。失败返回 None。"""
        raw = self._request(system_prompt, user_prompt, json_mode=True)
        if raw is None:
            return None

        return LLMResult(
            action=raw.get("action", "keep"),
            title=raw.get("title", ""),
            category=raw.get("category"),
            university_name=raw.get("university", ""),
            school_name=raw.get("school", ""),
            major_name=raw.get("major", ""),
            summary=raw.get("summary"),
            content=raw.get("content", ""),
            raw_response=raw,
        )

    def rewrite_content(self, system_prompt: str, user_prompt: str) -> str | None:
        """调用 LLM（非 JSON Mode），返回改写后的纯文本 content。失败返回 None。"""
        return self._request(system_prompt, user_prompt, json_mode=False)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _request(
        self, system_prompt: str, user_prompt: str, json_mode: bool = True
    ) -> dict | str | None:
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._do_request(system_prompt, user_prompt, json_mode)
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = self.retry_delay * attempt * 2
                    print(f"  [429] 等待 {wait}s ({attempt}/{self.max_retries})...")
                    time.sleep(wait)
                else:
                    err = e.read().decode("utf-8", errors="replace")[:200]
                    print(f"  [HTTP {e.code}] {err}")
                    if attempt < self.max_retries:
                        time.sleep(self.retry_delay)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"  [解析错误] {e} ({attempt}/{self.max_retries})")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
            except Exception as e:
                print(f"  [错误] {type(e).__name__}: {e}")
                if attempt < self.max_retries:
                    time.sleep(self.retry_delay)
        return None

    def _do_request(
        self, system_prompt: str, user_prompt: str, json_mode: bool
    ) -> dict | str:
        payload_dict: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode:
            payload_dict["response_format"] = {"type": "json_object"}

        payload = json.dumps(payload_dict).encode("utf-8")

        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        # 控制请求间隔
        elapsed = time.monotonic() - self._last_call_time
        if elapsed < self.request_interval:
            time.sleep(self.request_interval - elapsed)

        with urllib.request.urlopen(req) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        self._last_call_time = time.monotonic()

        text: str = body["choices"][0]["message"]["content"].strip()

        if json_mode:
            # JSON Mode: 返回 dict
            if "```" in text:
                m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
                if m:
                    text = m.group(1)
            return json.loads(text)
        else:
            # 纯文本: 去掉可能的 code block 包装，直接返回
            if text.startswith("```") and text.endswith("```"):
                text = re.sub(r"^```[a-z]*\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            return text
