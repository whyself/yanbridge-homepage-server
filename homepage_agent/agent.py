"""Small DeepSeek tool-calling agent for homepage teacher data.

This is intentionally independent from the old pipeline.  It only knows four
safe tools: crw_search, crw_scrape, find_post, update_post.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .config import AgentConfig
from .tools import AgentTools, tool_schemas


SYSTEM_PROMPT = """
You are a Yanbridge homepage teacher agent.

Goal: verify teacher/school/lab/recruitment information and maintain posts.

Rules:
1. Use crw_search/crw_scrape for web evidence.
2. Use find_post before update_post unless a dedupe_key is given.
3. update_post can create or update a post.
4. Never ask for SQL and never output SQL.
5. evidence must be an array of URLs only.
6. Prefer teacher_name_cn as the default teacher name; use teacher_name_en only if Chinese is unavailable.
7. Return a concise final summary: what you verified, what you changed, and evidence URLs.
""".strip()


class HomepageAgent:
    def __init__(self, config: AgentConfig | None = None, tools: AgentTools | None = None):
        self.config = config or AgentConfig()
        self.tools = tools or AgentTools(self.config)

    def run(self, task: str, max_steps: int = 8) -> str:
        if not self.config.deepseek_api_key:
            raise ValueError("Set DEEPSEEK_API_KEY before running agent mode.")

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        for _ in range(max_steps):
            message = self._chat(messages)
            messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return str(message.get("content") or "")

            for tool_call in tool_calls:
                fn = tool_call.get("function") or {}
                name = str(fn.get("name") or "")
                args = _json_dict(fn.get("arguments") or "{}")
                result = self.tools.call_tool(name, args)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return "Stopped: max tool steps reached."

    def start_session(
        self,
        on_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
    ) -> "HomepageAgentSession":
        return HomepageAgentSession(self, on_tool_call=on_tool_call)

    def close(self) -> None:
        self.tools.close()

    def _chat(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        payload = {
            "model": self.config.agent_model,
            "messages": messages,
            "tools": tool_schemas(),
            "tool_choice": "auto",
        }
        req = urllib.request.Request(
            self.config.deepseek_api_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.deepseek_api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"DeepSeek failed: HTTP {exc.code} {detail}") from exc
        return body["choices"][0]["message"]


def build_agent(config: AgentConfig | None = None, tools: AgentTools | None = None) -> HomepageAgent:
    return HomepageAgent(config=config, tools=tools)


class HomepageAgentSession:
    """Persistent chat session for interactive terminal use."""

    def __init__(
        self,
        agent: HomepageAgent,
        on_tool_call: Callable[[str, dict[str, Any], dict[str, Any]], None] | None = None,
    ):
        self.agent = agent
        self.on_tool_call = on_tool_call
        self.messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def ask(self, text: str, max_steps: int = 8) -> str:
        if not self.agent.config.deepseek_api_key:
            raise ValueError("Set DEEPSEEK_API_KEY before running agent mode.")

        self.messages.append({"role": "user", "content": text})
        for _ in range(max_steps):
            message = self.agent._chat(self.messages)
            self.messages.append(message)

            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return str(message.get("content") or "")

            for tool_call in tool_calls:
                fn = tool_call.get("function") or {}
                name = str(fn.get("name") or "")
                args = _json_dict(fn.get("arguments") or "{}")
                result = self.agent.tools.call_tool(name, args)
                if self.on_tool_call:
                    self.on_tool_call(name, args, result)
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.get("id"),
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )

        return "Stopped: max tool steps reached."


def _json_dict(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}
