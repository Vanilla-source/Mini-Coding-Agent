"""主循环：模型的"想"与工具"做"之间的循环。

    messages -> 模型 -> (工具调用? -> 执行 -> 结果回填) -> 模型 -> ... -> finish

三条硬性规则（对应课堂纪律）：
1. 全自动，不中途问人（考场只允许启动 / 给任务 / 配参数 / 展示结果）。
2. 必须能终止：finish 工具 + 最大轮数 + token 预算，三重保险。
3. 工具报错不算崩溃：错误文本回填给模型，让它自己修正。
"""

from __future__ import annotations

import time
from pathlib import Path

from . import context
from .config import Config
from .llm import AgentError, DeepSeekClient
from .logger import RunLogger
from .prompts import SYSTEM_PROMPT, task_prompt
from .tools import FINISH_SENTINEL, TOOL_SCHEMAS, ToolContext, dispatch

NUDGE = ("还没有完成任务。请继续用工具推进；如果已经完成，请先实际运行一次验证，"
         "然后调用 finish 结束。")


def run_agent(cfg: Config, task_text: str, run_dir: Path,
              workdir: Path | None = None, echo: bool = True) -> dict:
    """执行一次完整任务，返回运行结果摘要。"""
    run_dir = Path(run_dir)
    workspace = Path(workdir) if workdir else run_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    logger = RunLogger(run_dir, echo=echo)
    t0 = time.monotonic()

    result: dict = {
        "status": "unknown",
        "summary": "",
        "steps": 0,
        "usage": {},
        "elapsed_sec": 0.0,
        "run_dir": str(run_dir),
        "workspace": str(workspace),
    }

    try:
        client = DeepSeekClient(cfg)
    except AgentError as e:
        logger.info(f"[启动失败] {e}")
        result.update(status="error", summary=str(e))
        logger.close()
        return result

    ctx = ToolContext(workspace=workspace, logger=logger, cfg=cfg)
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task_prompt(task_text, str(workspace))},
    ]

    logger.event("run_start", model=cfg.model, workspace=str(workspace),
                 max_steps=cfg.max_steps, token_budget=cfg.token_budget)
    logger.info(f"模型={cfg.model}  工作目录={workspace}")

    nudges = 0
    status = "max_steps"
    summary = ""

    try:
        for step in range(1, cfg.max_steps + 1):
            result["steps"] = step
            reply = client.chat(messages, tools=TOOL_SCHEMAS)
            content = reply["content"]
            calls = reply["tool_calls"]

            logger.model_message(step, content, [c["name"] for c in calls], reply["usage"])
            if content.strip():
                logger.info(f"  step {step:02d} 模型: {content.strip()[:160]}")

            # 没有工具调用：模型在"说话"，催一次；连续两次就直接收手
            if not calls:
                messages.append(reply["assistant_message"])
                nudges += 1
                if nudges >= 2:
                    status = "no_tool_calls"
                    summary = content.strip()[:200]
                    logger.info("模型连续未调用工具，结束运行")
                    break
                messages.append({"role": "user", "content": NUDGE})
                continue

            nudges = 0
            messages.append(reply["assistant_message"])

            finished = False
            for call in calls:
                logger.tool_call(step, call["name"], call["arguments"])
                t_tool = time.monotonic()
                output, is_error = dispatch(ctx, call["name"], call["arguments"])
                logger.tool_result(step, call["name"], not is_error, output,
                                   int((time.monotonic() - t_tool) * 1000))

                if call["name"] == "finish" and FINISH_SENTINEL in output:
                    summary = output.split("|", 1)[1] if "|" in output else ""
                    finished = True
                    # finish 也要给模型一条 tool 消息，保持消息序列合法
                    messages.append({"role": "tool", "tool_call_id": call["id"],
                                     "content": f"已记录完成信号：{summary}"})
                    continue

                messages.append({"role": "tool", "tool_call_id": call["id"],
                                 "content": output})

            if finished:
                status = "finished"
                break

            messages = context.trim(messages, cfg.keep_recent)

            if client.usage.total > cfg.token_budget:
                status = "budget_exceeded"
                summary = f"token 用量 {client.usage.total} 超过预算 {cfg.token_budget}"
                logger.info(summary)
                break

    except AgentError as e:
        status, summary = "error", str(e)
        logger.info(f"[致命错误] {e}")
    except KeyboardInterrupt:
        status, summary = "interrupted", "用户中断"
        logger.info("用户中断")
    except Exception as e:  # noqa: BLE001
        status, summary = "error", f"{type(e).__name__}: {e}"
        logger.info(f"[异常] {summary}")

    result.update(status=status, summary=summary,
                  usage=client.usage.as_dict(),
                  elapsed_sec=round(time.monotonic() - t0, 1))
    logger.event("run_finish", **{k: v for k, v in result.items() if k != "run_dir"})
    logger.info(f"结束：{status}｜{summary or '无说明'}")
    logger.info(f"用量：{client.usage.as_dict()}｜耗时 {result['elapsed_sec']}s")
    logger.close()
    return result
