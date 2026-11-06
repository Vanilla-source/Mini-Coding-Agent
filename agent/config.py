"""配置加载。

设计原则：
1. 所有配置来自环境变量 / .env，**不依赖任何交互式输入**（课堂考核不允许中途操作）。
2. 每项都有安全默认值，缺什么都不至于直接崩。
3. 命令行参数可以覆盖，但只覆盖模型与轮数这类无害项。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = PROJECT_ROOT / "runs"


@dataclass(frozen=True)
class Config:
    """一次运行所需的全部参数。"""

    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-chat"

    # 生成参数
    temperature: float = 0.2

    # 循环控制
    max_steps: int = 25
    token_budget: int = 200_000

    # 工具执行
    exec_timeout: int = 30          # 单次子进程超时（秒）
    device_check_timeout: int = 300  # 预留：任务三训练类长任务

    # 工具输出截断（防止一次 traceback 吃掉几万 token）
    head_lines: int = 60
    tail_lines: int = 40
    max_output_chars: int = 8000

    # 上下文管理
    keep_recent: int = 12

    def with_overrides(self, **kwargs) -> "Config":
        """返回覆盖了部分字段的新配置（frozen dataclass 不可原地改）。"""
        clean = {k: v for k, v in kwargs.items() if v is not None}
        return replace(self, **clean) if clean else self

    @property
    def has_key(self) -> bool:
        return bool(self.api_key) and self.api_key != "sk-your-key-here"


def load_config(model: str | None = None,
                max_steps: int | None = None,
                env_file: Path | None = None) -> Config:
    """从 .env 与环境变量组装配置，再叠加命令行覆盖。"""
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file or (PROJECT_ROOT / ".env"), override=False)
    except ImportError:
        # 允许在未安装依赖时也能 import 本模块（smoke.py 会给出明确提示）
        pass

    def _get(name: str, default: str) -> str:
        return (os.getenv(name) or default).strip()

    def _get_int(name: str, default: int) -> int:
        try:
            return int(_get(name, str(default)))
        except ValueError:
            return default

    def _get_float(name: str, default: float) -> float:
        try:
            return float(_get(name, str(default)))
        except ValueError:
            return default

    cfg = Config(
        api_key=_get("DEEPSEEK_API_KEY", ""),
        base_url=_get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=_get("DEEPSEEK_MODEL", "deepseek-chat"),
        temperature=_get_float("AGENT_TEMPERATURE", 0.2),
        max_steps=_get_int("AGENT_MAX_STEPS", 25),
        token_budget=_get_int("AGENT_TOKEN_BUDGET", 200_000),
        exec_timeout=_get_int("AGENT_EXEC_TIMEOUT", 30),
        keep_recent=_get_int("AGENT_KEEP_RECENT", 12),
    )
    return cfg.with_overrides(model=model, max_steps=max_steps)
