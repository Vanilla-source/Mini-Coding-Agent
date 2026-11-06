"""跑模拟题并汇总得分。

    python scripts/grade.py            # 跑全部
    python scripts/grade.py task1      # 只跑某一个

骨架阶段：只负责"发现题目 -> 逐个调用 Agent -> 记录指标"，判分逻辑随题目一起补。
评测目录约定（后续按此补齐）：

    eval/<task_id>/
        task.md         给 Agent 的任务描述（会原样作为 task.txt）
        data/           教师式输入数据（train.csv / features.csv / 待修源码等）
        grade.py        该题的判分脚本，提供 grade(workspace) -> (score, detail)
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

EVAL_DIR = ROOT / "eval"
REPORTS = ROOT / "runs" / "eval-report"


def discover(only: str | None) -> list[Path]:
    if not EVAL_DIR.exists():
        return []
    tasks = sorted(p for p in EVAL_DIR.iterdir() if p.is_dir() and (p / "task.md").exists())
    if only:
        tasks = [p for p in tasks if only in p.name]
    return tasks


def load_grader(task_dir: Path):
    """加载某题的判分脚本。没有就返回 None（骨架阶段允许缺失）。"""
    gp = task_dir / "grade.py"
    if not gp.exists():
        return None
    spec = importlib.util.spec_from_file_location(f"grader_{task_dir.name}", gp)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def prepare_workspace(task_dir: Path, workdir: Path) -> None:
    """把该题的输入数据拷进工作目录（不改动原始数据）。"""
    src = task_dir / "data"
    if not src.exists():
        return
    import shutil
    for item in src.iterdir():
        dest = workdir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)


def run_one(task_dir: Path) -> dict:
    from agent.config import load_config
    from agent.loop import run_agent

    task_text = (task_dir / "task.md").read_text(encoding="utf-8")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = ROOT / "runs" / f"{stamp}-eval-{task_dir.name}"
    workdir = run_dir / "workspace"
    workdir.mkdir(parents=True, exist_ok=True)
    prepare_workspace(task_dir, workdir)

    print(f"\n>>> {task_dir.name}  ->  {run_dir}")
    t0 = time.monotonic()
    result = run_agent(load_config(), task_text, run_dir, workdir=workdir, echo=True)
    elapsed = round(time.monotonic() - t0, 1)

    score, detail = None, "未提供判分脚本"
    grader = load_grader(task_dir)
    if grader is not None:
        try:
            score, detail = grader.grade(workdir)          # type: ignore[attr-defined]
        except Exception as e:  # noqa: BLE001
            detail = f"判分异常：{type(e).__name__}: {e}"

    return {
        "task": task_dir.name,
        "status": result["status"],
        "steps": result["steps"],
        "elapsed_sec": elapsed,
        "usage": result["usage"],
        "score": score,
        "detail": detail,
        "run_dir": str(run_dir),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?", default=None, help="只跑名字里包含该关键字的题")
    args = ap.parse_args()

    tasks = discover(args.only)
    if not tasks:
        print("eval/ 下还没有可跑的题目（需要 eval/<task>/task.md）。")
        print("先按开发计划第 3 节补三道模拟题。")
        return 1

    rows = [run_one(t) for t in tasks]

    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"eval-{datetime.now():%Y%m%d-%H%M%S}.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 78)
    print(f"{'任务':<28}{'状态':<12}{'轮数':<6}{'耗时':<8}{'得分':<8}")
    print("-" * 78)
    for r in rows:
        print(f"{r['task']:<28}{r['status']:<12}{r['steps']:<6}"
              f"{r['elapsed_sec']:<8}{str(r['score']):<8}")
    print("=" * 78)
    print(f"明细已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
