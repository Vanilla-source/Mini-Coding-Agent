"""DeepSeek 客户端封装。

只做三件事，其余交给主循环：
1. 调用（OpenAI 兼容协议，改 base_url 即可）
2. 重试（只对超时/连接/限流/5xx 重试，认证错误立即失败）
3. 归一化：把 SDK 对象转成主循环好处理的字典，并累计 token 用量
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import (APIConnectionError, APITimeoutError, AuthenticationError,
                    InternalServerError, OpenAI, RateLimitError)
from tenacity import (retry, retry_if_exception_type, stop_after_attempt,
                      wait_exponential_jitter)

from .config import Config

RETRYABLE = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class AgentError(RuntimeError):
    """代理层面的致命错误（缺 key、认证失败等）。"""


@dataclass
class Usage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def as_dict(self) -> dict:
        return {"calls": self.calls, "prompt": self.prompt_tokens,
                "completion": self.completion_tokens, "total": self.total}


class DeepSeekClient:
    def __init__(self, cfg: Config):
        if not cfg.has_key:
            raise AgentError(
                "未配置 DEEPSEEK_API_KEY。请复制 .env.example 为 .env 并填入自己的 key。")
        self.cfg = cfg
        self.usage = Usage()
        # max_retries=0：重试由下面的 tenacity 统一接管，避免 SDK 内部再重试导致耗时翻倍
        self._client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url,
                              timeout=180.0, max_retries=0)

    @retry(retry=retry_if_exception_type(RETRYABLE),
           stop=stop_after_attempt(3),
           wait=wait_exponential_jitter(initial=2, max=20),
           reraise=True)
    def _create(self, **kwargs: Any):
        return self._client.chat.completions.create(**kwargs)

    def chat(self, messages: list[dict], tools: list[dict] | None = None) -> dict:
        """调用一次模型，返回归一化结果。

        返回结构：
            {
              "content": str,                  # 模型的自然语言回复
              "tool_calls": [{"id","name","arguments"(dict)}],
              "assistant_message": {...},      # 可直接 append 进 messages 的原始消息
              "usage": {...},
              "finish_reason": str,
            }
        """
        kwargs: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "temperature": self.cfg.temperature,
            "max_tokens": 4096,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            resp = self._create(**kwargs)
        except AuthenticationError as e:
            raise AgentError(f"API Key 无效或已过期：{e}") from e

        choice = resp.choices[0]
        message = choice.message
        content = message.content or ""

        raw_calls = getattr(message, "tool_calls", None) or []
        assistant_message: dict[str, Any] = {"role": "assistant", "content": content}
        normalized: list[dict] = []

        if raw_calls:
            assistant_message["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name,
                              "arguments": tc.function.arguments}}
                for tc in raw_calls
            ]
            for tc in raw_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                    if not isinstance(args, dict):
                        args = {}
                except json.JSONDecodeError:
                    args = {}
                normalized.append({"id": tc.id, "name": tc.function.name,
                                   "arguments": args})

        usage = getattr(resp, "usage", None)
        self.usage.calls += 1
        if usage is not None:
            self.usage.prompt_tokens += getattr(usage, "prompt_tokens", 0) or 0
            self.usage.completion_tokens += getattr(usage, "completion_tokens", 0) or 0

        return {
            "content": content,
            "tool_calls": normalized,
            "assistant_message": assistant_message,
            "usage": self.usage.as_dict(),
            "finish_reason": getattr(choice, "finish_reason", "") or "",
        }
