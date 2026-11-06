"""运行日志与脱敏。

两种日志同时写：
- trace.jsonl：结构化，一行一个事件，便于事后统计（轮数、工具调用次数、耗时）。
- agent.log：人类可读，课堂演示与报告截图用这一份。

纪律要求：日志中不得出现 API Key。所有写盘内容统一走 _redact()。
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

# sk- 开头、长度足够的字符串一律视为密钥
_SECRET_PAT = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")
_SENSITIVE_KEYS = {"api_key", "apikey", "authorization", "token", "secret"}


def redact(value: Any) -> Any:
    """递归脱敏：字符串替换 sk-xxx，字典按 key 名遮蔽。"""
    if isinstance(value, str):
        return _SECRET_PAT.sub("sk-***REDACTED***", value)
    if isinstance(value, dict):
        return {
            k: ("***REDACTED***" if k.lower() in _SENSITIVE_KEYS else redact(v))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class RunLogger:
    """一次运行对应一个 RunLogger，落盘到 runs/<id>/。"""

    def __init__(self, run_dir: Path, echo: bool = False):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.echo = echo
        self.trace_path = self.run_dir / "trace.jsonl"
        self.text_path = self.run_dir / "agent.log"
        self._trace: TextIO = self.trace_path.open("a", encoding="utf-8", buffering=1)
        self._text: TextIO = self.text_path.open("a", encoding="utf-8", buffering=1)
        self._t0 = time.monotonic()

    # ---------- 写入 ----------

    def event(self, name: str, **fields: Any) -> None:
        """写一条结构化事件。"""
        record = {
            "ts": datetime.now().isoformat(timespec="milliseconds"),
            "event": name,
            "elapsed_ms": int((time.monotonic() - self._t0) * 1000),
        }
        record.update(redact(fields))
        self._trace.write(json.dumps(record, ensure_ascii=False) + "\n")

    def info(self, message: str) -> None:
        """写一行人类可读日志（同时进 trace）。"""
        line = redact(message)
        if self.echo:
            print(line, flush=True)
        self._text.write(f"[{datetime.now():%H:%M:%S}] {line}\n")
        self._trace.write(json.dumps(
            {"ts": datetime.now().isoformat(timespec="milliseconds"),
             "event": "info", "message": line},
            ensure_ascii=False) + "\n")

    def tool_call(self, step: int, name: str, args: dict) -> None:
        shown = json.dumps(redact(args), ensure_ascii=False)
        if len(shown) > 400:
            shown = shown[:400] + " ..."
        self.info(f"  step {step:02d} -> {name} {shown}")
        self.event("tool_call", step=step, tool=name, args=args)

    def tool_result(self, step: int, name: str, ok: bool, output: str,
                    elapsed_ms: int = 0) -> None:
        preview = output.replace("\n", " ")[:200]
        self.info(f"  step {step:02d} <- {name} [{'ok' if ok else 'error'}] {preview}")
        self.event("tool_result", step=step, tool=name, ok=ok,
                   elapsed_ms=elapsed_ms, output_chars=len(output),
                   output_head=output[:2000])

    def model_message(self, step: int, content: str | None,
                      tool_names: list[str], tokens: dict) -> None:
        self.event("model_message", step=step,
                   content=(content or "")[:2000],
                   tool_calls=tool_names, tokens=tokens)

    # ---------- 收尾 ----------

    def close(self) -> None:
        self.event("run_end")
        for f in (self._trace, self._text):
            try:
                f.close()
            except Exception:
                pass

    def __enter__(self) -> "RunLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
