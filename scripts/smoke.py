"""环境自检。

在写任何业务代码之前先跑这个：七项全绿，说明环境没问题；
任何一项 FAIL/SKIP，说明后面所有工作都会卡住，先把这一项解决。

    python scripts/smoke.py
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

RESULTS: list[tuple[str, str, str]] = []   # (状态, 名称, 说明)


def record(status: str, name: str, detail: str = "") -> None:
    RESULTS.append((status, name, detail))
    icon = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
    print(f"{icon} {name}" + (f"  —— {detail}" if detail else ""))


# ------------------------------------------------------------------ 1. Python
def check_python() -> None:
    v = sys.version_info
    detail = f"{v.major}.{v.minor}.{v.micro} @ {sys.executable}"
    if (v.major, v.minor) >= (3, 10):
        record("PASS", "Python 版本 >= 3.10", detail)
    else:
        record("FAIL", "Python 版本 >= 3.10", detail + "（请升级到 3.10~3.12）")


# --------------------------------------------------------------- 2. 依赖包
DEPS = ["openai", "dotenv", "tenacity", "rich", "numpy", "pandas", "sklearn", "pytest"]


def check_deps() -> None:
    missing = []
    for mod in DEPS:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(mod)
    if not missing:
        record("PASS", "依赖包导入", " ".join(DEPS))
    else:
        record("FAIL", "依赖包导入",
               f"缺少 {', '.join(missing)}  ->  pip install -r requirements.txt")


# ------------------------------------------------------------- 3. 内置工具
def check_tools() -> None:
    try:
        from agent.tools import ToolContext, dispatch

        # 放在项目内的 runs/ 下，避免部分环境限制系统临时目录的可写权限
        tmp = ROOT / "runs" / "_smoke_tools"
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        ctx = ToolContext(workspace=tmp)

        out, err = dispatch(ctx, "write_file",
                            {"path": "hello.py", "content": "print('hello from agent')\n"})
        assert not err, out

        out, err = dispatch(ctx, "read_file", {"path": "hello.py"})
        assert not err and "hello from agent" in out, out

        out, err = dispatch(ctx, "run_python", {"path": "hello.py"})
        assert not err and "hello from agent" in out, out

        # 越界保护
        out, err = dispatch(ctx, "read_file", {"path": "../../etc/passwd"})
        assert err, "路径越界未被拦截"

        shutil.rmtree(tmp, ignore_errors=True)
        record("PASS", "内置工具（写/读/执行/越界保护）")
    except Exception:
        record("FAIL", "内置工具", traceback.format_exc(limit=2).replace("\n", " ")[:200])


# ----------------------------------------------------------- 4. 子进程执行
def check_subprocess() -> None:
    try:
        proc = subprocess.run(
            [sys.executable, "-c", "import sys; print('ok'); sys.exit(0)"],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode == 0 and "ok" in proc.stdout:
            record("PASS", "子进程执行", f"{sys.version_info.major}.{sys.version_info.minor}")
        else:
            record("FAIL", "子进程执行", proc.stderr.strip()[:160])
    except Exception as e:
        record("FAIL", "子进程执行", f"{type(e).__name__}: {e}")


# ------------------------------------------------------------------ 5. torch
def check_torch() -> None:
    try:
        import torch
    except Exception:
        record("SKIP", "PyTorch", "未安装 -> pip install torch --index-url "
                                   "https://download.pytorch.org/whl/cpu")
        return
    try:
        cuda = torch.cuda.is_available()
        x = torch.randn(2, 3)
        y = (x @ x.T).sum().item()
        detail = f"torch {torch.__version__}，CUDA={'有' if cuda else '无（考核要求 CPU）'}，" \
                 f"算力自检 {y:.3f}"
        record("PASS", "PyTorch", detail)
    except Exception as e:
        record("FAIL", "PyTorch", f"{type(e).__name__}: {e}")


# ------------------------------------------------------------- 6. API 配置
def check_env() -> tuple[bool, str, str]:
    env_path = ROOT / ".env"
    if not env_path.exists():
        record("FAIL", ".env 配置", "缺少 .env -> copy .env.example .env 后填入 key")
        return False, "", ""
    try:
        from agent.config import load_config
        cfg = load_config()
    except Exception as e:
        record("FAIL", ".env 配置", f"{type(e).__name__}: {e}")
        return False, "", ""

    if cfg.has_key:
        masked = cfg.api_key[:6] + "..." + cfg.api_key[-4:] if len(cfg.api_key) > 12 else "***"
        record("PASS", ".env 配置", f"key={masked}  model={cfg.model}")
        return True, cfg.api_key, cfg.model

    record("FAIL", ".env 配置", "DEEPSEEK_API_KEY 为空或仍是占位符")
    return False, "", ""


# ------------------------------------------------------------- 7. API 连通
def check_api(has_key: bool, api_key: str, model: str) -> None:
    if not has_key:
        record("SKIP", "DeepSeek API 连通", "缺少 key，无法测试")
        return
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com",
                        timeout=60, max_retries=0)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "只回复两个字：正常"}],
            max_tokens=16, temperature=0,
        )
        text = (resp.choices[0].message.content or "").strip()
        record("PASS", "DeepSeek API 连通", f"模型 {model} 回复：{text[:20]}")
    except Exception as e:
        record("FAIL", "DeepSeek API 连通", f"{type(e).__name__}: {str(e)[:180]}")


# -------------------------------------------------------------------- main
def main() -> int:
    print("=" * 68)
    print("  Mini Coding Agent 环境自检")
    print("=" * 68)

    check_python()
    check_deps()
    check_tools()
    check_subprocess()
    check_torch()
    has_key, api_key, model = check_env()
    check_api(has_key, api_key, model)

    n_pass = sum(1 for s, _, _ in RESULTS if s == "PASS")
    n_fail = sum(1 for s, _, _ in RESULTS if s == "FAIL")
    n_skip = sum(1 for s, _, _ in RESULTS if s == "SKIP")

    print("-" * 68)
    print(f"  通过 {n_pass}｜失败 {n_fail}｜跳过 {n_skip}   共 {len(RESULTS)} 项")
    if n_fail == 0 and n_skip == 0:
        print("  环境就绪，可以开始：python -m agent.main --task \"...\"")
        print("-" * 68)
        return 0
    print("  还有未通过/未完成的检查项，先按上面的提示处理。")
    print("-" * 68)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
