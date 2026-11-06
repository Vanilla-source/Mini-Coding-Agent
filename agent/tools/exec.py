"""执行类工具：run_python / run_pytest。

三个必做细节：
1. 超时后连子进程树一起杀掉（PyTorch 训练会派生子进程，只杀父进程会留下僵尸）。
2. 输出先截断再返回，保留头尾，中间标省略行数。
3. 显式设置 UTF-8，避免 Windows 控制台编码导致中文报错乱码。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from . import ToolContext, ToolError
from .fs import resolve_path

DEFAULT_RUN_TIMEOUT = 30
DEFAULT_PYTEST_TIMEOUT = 60


# ------------------------------------------------------------------ 公共

def truncate_output(text: str, head: int = 60, tail: int = 40,
                    max_chars: int = 8000) -> str:
    """头尾保留式截断。中间用一行标记代替，防止上下文被一次报错灌满。"""
    if not text:
        return "(无输出)"

    lines = text.splitlines()
    if len(lines) > head + tail:
        omitted = len(lines) - head - tail
        lines = lines[:head] + [f"... [已截断 {omitted} 行] ..."] + lines[-tail:]
    out = "\n".join(lines)

    if len(out) > max_chars:
        out = out[:max_chars] + f"\n... [输出过长，已截断，原始共 {len(text)} 字符] ..."
    return out


def _env() -> dict:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.pop("PYTHONPATH", None)   # 避免工作目录里的同名模块被意外导入
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    """连子进程一起杀掉。"""
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, check=False)
    else:
        proc.kill()


def _run(cmd: list[str], cwd: Path, timeout: int) -> tuple[int, str, bool]:
    """执行命令，返回 (退出码, 合并后的输出, 是否超时)。"""
    try:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
            env=_env(),
        )
    except FileNotFoundError as e:
        raise ToolError(f"无法启动进程：{e}") from e

    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", False
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        out, _ = proc.communicate()
        return proc.returncode if proc.returncode is not None else -1, out or "", True


# --------------------------------------------------------------- run_python

def run_python(ctx: ToolContext, path: str, args: list[str] | None = None,
               timeout: int = 0) -> str:
    target = resolve_path(ctx, path)
    if not target.exists():
        return f"ERROR: 脚本不存在：{path}"
    if target.suffix != ".py":
        return f"ERROR: {path} 不是 .py 文件"

    cfg = ctx.cfg
    limit = int(timeout or (getattr(cfg, "exec_timeout", DEFAULT_RUN_TIMEOUT)))
    limit = max(1, min(limit, 600))

    t0 = time.monotonic()
    code, out, timed_out = _run(
        [sys.executable, str(target), *[str(a) for a in (args or [])]],
        cwd=Path(ctx.workspace).resolve(),
        timeout=limit,
    )
    elapsed = int((time.monotonic() - t0) * 1000)

    head = getattr(cfg, "head_lines", 60)
    tail = getattr(cfg, "tail_lines", 40)
    max_chars = getattr(cfg, "max_output_chars", 8000)

    body = truncate_output(out, head, tail, max_chars)
    status = "超时被终止" if timed_out else ("成功" if code == 0 else "失败")
    return (f"[run_python] {path} -> 退出码 {code}，{status}，耗时 {elapsed} ms\n"
            f"--- 输出 ---\n{body}")


# --------------------------------------------------------------- run_pytest

_PYTEST_SUMMARY = re.compile(
    r"^(?:=+\s*)?(\d+ (?:passed|failed|error|errors|skipped).*?)(?:\s*=+)?$", re.M)


def _summarize_pytest(out: str) -> str:
    """从 pytest 输出里抽出最后一行的结果概览。"""
    matches = [m.group(1).strip() for m in _PYTEST_SUMMARY.finditer(out)]
    return matches[-1] if matches else "(未解析到测试结果)"


def run_pytest(ctx: ToolContext, path: str = ".", timeout: int = 0) -> str:
    limit = int(timeout or DEFAULT_PYTEST_TIMEOUT)
    limit = max(1, min(limit, 900))

    target = resolve_path(ctx, path)
    if not target.exists():
        return f"ERROR: 路径不存在：{path}"

    cfg = ctx.cfg
    t0 = time.monotonic()
    code, out, timed_out = _run(
        [sys.executable, "-m", "pytest", str(target), "-q", "--tb=short",
         "-p", "no:cacheprovider"],
        cwd=Path(ctx.workspace).resolve(),
        timeout=limit,
    )
    elapsed = int((time.monotonic() - t0) * 1000)

    body = truncate_output(out,
                           getattr(cfg, "head_lines", 60),
                           getattr(cfg, "tail_lines", 40),
                           getattr(cfg, "max_output_chars", 8000))
    status = "超时被终止" if timed_out else ("全部通过" if code == 0 else "存在失败")
    return (f"[run_pytest] {path} -> 退出码 {code}，{status}，耗时 {elapsed} ms\n"
            f"摘要：{_summarize_pytest(out)}\n--- 输出 ---\n{body}")
