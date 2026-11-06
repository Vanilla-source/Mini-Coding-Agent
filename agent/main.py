"""命令行入口。

    python -m agent.main --task-file task.txt
    python -m agent.main --task "实现一个支持 get/put 的 LRU Cache"

设计要点：参数全部可有默认值、全程无交互，考场上一条命令跑完。
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from .config import RUNS_DIR, load_config
from .loop import run_agent


def _slug(text: str, limit: int = 24) -> str:
    """从任务文本里取一段可做目录名的短标识。"""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text.strip())
    cleaned = cleaned.strip("-")
    return (cleaned[:limit] or "task").rstrip("-")


def _read_task(args) -> str:
    if args.task_file:
        path = Path(args.task_file)
        if not path.exists():
            raise SystemExit(f"任务文件不存在：{path}")
        return path.read_text(encoding="utf-8")
    if args.task:
        return args.task
    raise SystemExit("必须提供 --task 或 --task-file")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m agent.main",
        description="基于 DeepSeek API 的 Mini Coding Agent",
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--task", help="任务描述（直接给一段文字）")
    src.add_argument("--task-file", help="任务文件路径（推荐，考场上原样保存题目）")
    p.add_argument("--workdir", default="auto",
                   help="被测代码的工作目录；auto 表示 runs/<id>/workspace")
    p.add_argument("--model", default=None, help="覆盖 .env 里的模型名")
    p.add_argument("--max-steps", type=int, default=None, help="覆盖最大轮数")
    p.add_argument("--quiet", action="store_true", help="不在终端回显过程日志")
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    args = build_parser().parse_args(argv)
    task_text = _read_task(args)
    cfg = load_config(model=args.model, max_steps=args.max_steps)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = RUNS_DIR / f"{stamp}-{_slug(task_text)}"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "task.txt").write_text(task_text, encoding="utf-8")

    workdir = None
    if args.workdir and args.workdir != "auto":
        workdir = Path(args.workdir).expanduser().resolve()
        workdir.mkdir(parents=True, exist_ok=True)

    if not args.quiet:
        print("=" * 68)
        print(f"  Mini Coding Agent  |  模型 {cfg.model}  |  最多 {cfg.max_steps} 轮")
        print(f"  任务：{task_text.strip().splitlines()[0][:56]}")
        print(f"  输出：{run_dir}")
        print("=" * 68)

    result = run_agent(cfg, task_text, run_dir, workdir=workdir, echo=not args.quiet)

    print("-" * 68)
    print(f"  状态：{result['status']}    轮数：{result['steps']}    "
          f"耗时：{result['elapsed_sec']}s")
    print(f"  说明：{result['summary'] or '（无）'}")
    print(f"  用量：{result['usage']}")
    print(f"  产物：{result['run_dir']}")
    print("-" * 68)

    return 0 if result["status"] == "finished" else 1


if __name__ == "__main__":
    raise SystemExit(main())
