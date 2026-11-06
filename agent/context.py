"""上下文管理。

模型不会记得无限长的历史，而一次 run_python 的报错就可能上千 token。
这里的职责只有两件事：
1. 无状态裁剪：只留最近若干轮，且保证不切断 "assistant(tool_calls) -> tool" 的配对。
2. 预算判断：给主循环一个"该不该收手"的依据。

摘要压缩（把早期轮次压成一段"已验证/已失败"的总结）目前只留接口，后续实现。
"""

from __future__ import annotations

from typing import Any

Message = dict[str, Any]


def trim(messages: list[Message], keep_recent: int = 12) -> list[Message]:
    """保留 system + 首个 user + 最近 keep_recent 条，其余丢弃。

    裁剪点必须落在"工具调用边界"上，否则会留下孤立的 tool 消息，
    DeepSeek / OpenAI 接口会直接报 400。
    """
    if len(messages) <= keep_recent + 2:
        return messages

    head = messages[:2]                 # system + 首个 user 任务描述
    tail = messages[-keep_recent:]

    # 从尾部窗口开头剥掉孤立的 tool 消息及其对应的 assistant 调用
    while tail and tail[0].get("role") == "tool":
        tail.pop(0)

    # 如果窗口开头恰好是带 tool_calls 的 assistant，也一并保留其后的 tool 结果（本来就连续）
    return head + tail


def estimate_tokens(messages: list[Message]) -> int:
    """粗略估算 token：中文约 1 字 1 token，英文约 4 字符 1 token。

    只用于预算告警，不要求精确，所以直接按字符数 / 1.6 估。
    """
    total = 0
    for m in messages:
        content = m.get("content") or ""
        if isinstance(content, list):
            content = " ".join(str(c) for c in content)
        total += len(str(content))
        for tc in (m.get("tool_calls") or []):
            total += len(str(tc))
    return int(total / 1.6)


def needs_compression(messages: list[Message], max_chars: int = 120_000) -> bool:
    """上下文是否已经过长（需要压缩或丢弃早期轮次）。"""
    return sum(len(str(m.get("content") or "")) for m in messages) > max_chars


def compress(messages: list[Message], summarizer=None) -> list[Message]:
    """把最早的若干轮压成一段摘要。

    TODO(第二阶段实现)：
      - 取 messages[2:-keep_recent] 里"工具调用 + 结果的一句话概括"
      - 调一次模型生成 "已确认的事实 / 已失败的尝试" 两类要点
      - 用一条 role=system 的摘要消息替换掉这些轮次
    目前直接退化为 trim()，保证不会因为缺实现而崩。
    """
    if summarizer is None:
        return trim(messages)
    return summarizer(messages)
