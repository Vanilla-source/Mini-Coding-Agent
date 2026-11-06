"""完成信号。

单独成一个工具，而不是让模型"回一句'做完了'"：
- 主循环能明确区分"任务完成"和"模型在解释思路"；
- 参数本身带上 summary，直接作为运行结论写进日志和报告。
"""

from __future__ import annotations

from . import ToolContext


def finish(ctx: ToolContext, summary: str = "") -> str:
    summary = (summary or "").strip() or "(模型未给出说明)"
    return f"__TASK_FINISHED__|{summary}"
