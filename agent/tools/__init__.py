"""工具集：注册表、JSON Schema 与分发。

每个工具都是 `(ctx, **kwargs) -> str`，返回值一律是**给模型看的文本**。
工具内部异常不向上抛，转成 "ERROR: ..." 文本返回，让模型自己纠错——这正是
"根据运行错误自动尝试修正"的能力来源。

注意：子模块的 import 必须放在 ToolContext 定义之后，否则 fs/exec/finish
在导入 `from . import ToolContext` 时会撞上尚未初始化完成的包。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

FINISH_SENTINEL = "__TASK_FINISHED__"


class ToolError(Exception):
    """工具层面的可预期错误（路径越界、文件不存在等）。"""


@dataclass
class ToolContext:
    """一次运行内所有工具共享的上下文。"""

    workspace: Path
    logger: Any = None
    cfg: Any = None


def _schema(name: str, description: str, properties: dict,
            required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOL_SCHEMAS: list[dict] = [
    _schema(
        "list_dir",
        "列出工作目录下某路径的文件与子目录（不递归）。开始任务时先调用它了解现状。",
        {"path": {"type": "string", "description": "相对工作目录的路径，默认 '.'"}},
    ),
    _schema(
        "read_file",
        "读取文本文件，返回带行号的内容。文件很长时用 start_line/end_line 分段读取。",
        {
            "path": {"type": "string", "description": "相对工作目录的文件路径"},
            "start_line": {"type": "integer", "description": "起始行号，从 1 开始"},
            "end_line": {"type": "integer", "description": "结束行号（含）；0 表示读到文件末尾"},
        },
        ["path"],
    ),
    _schema(
        "write_file",
        "把内容整体写入文件（覆盖已有内容，自动创建父目录）。用于新建文件或整体重写。",
        {
            "path": {"type": "string", "description": "相对工作目录的文件路径"},
            "content": {"type": "string", "description": "完整的文件内容"},
        },
        ["path", "content"],
    ),
    _schema(
        "replace_in_file",
        "在文件中精确替换一段文本 old_string -> new_string。改代码时优先用它，改动最小、最安全。"
        "old_string 必须与文件中的内容完全一致（含缩进），且最好只出现一次。",
        {
            "path": {"type": "string", "description": "相对工作目录的文件路径"},
            "old_string": {"type": "string", "description": "要被替换的原文片段"},
            "new_string": {"type": "string", "description": "替换后的新内容；传空串表示删除"},
        },
        ["path", "old_string", "new_string"],
    ),
    _schema(
        "run_python",
        "在工具环境里执行一个 Python 脚本，返回 stdout、stderr 和退出码。"
        "脚本路径相对工作目录。输出过长会被截断（保留头尾）。",
        {
            "path": {"type": "string", "description": "要执行的 .py 文件路径"},
            "args": {"type": "array", "items": {"type": "string"},
                     "description": "传给脚本的命令行参数，可省略"},
            "timeout": {"type": "integer",
                        "description": "超时秒数，省略则用默认值（30 秒）"},
        },
        ["path"],
    ),
    _schema(
        "run_pytest",
        "在工作目录里运行 pytest，返回通过/失败摘要与失败用例。"
        "用于验证实现是否满足测试要求，也用于回归测试（确认原有功能未被改坏）。",
        {
            "path": {"type": "string",
                     "description": "测试文件或目录，默认 '.'（整个工作目录）"},
            "timeout": {"type": "integer", "description": "超时秒数，默认 60"},
        },
    ),
    _schema(
        "finish",
        "声明任务完成。只有在代码已写完整、且程序或测试已实际运行通过时才可调用。",
        {"summary": {"type": "string", "description": "一句话说明完成了什么、验证方式是什么"}},
        ["summary"],
    ),
]


# 子模块放在 ToolContext 之后导入（见文件头说明）
from . import exec as _exec  # noqa: E402
from . import finish as _finish  # noqa: E402
from . import fs as _fs  # noqa: E402


_DISPATCH: dict[str, Callable[..., str]] = {
    "list_dir": _fs.list_dir,
    "read_file": _fs.read_file,
    "write_file": _fs.write_file,
    "replace_in_file": _fs.replace_in_file,
    "run_python": _exec.run_python,
    "run_pytest": _exec.run_pytest,
    "finish": _finish.finish,
}


def dispatch(ctx: ToolContext, name: str, args: dict | None) -> tuple[str, bool]:
    """执行一个工具调用，返回 (给模型的文本, 是否为错误)。

    任何异常都被转成可读错误文本，保证主循环不会因为模型乱传参数而中断。
    """
    fn = _DISPATCH.get(name)
    if fn is None:
        return f"ERROR: 未知工具 {name!r}，可用工具：{', '.join(_DISPATCH)}", True

    try:
        result = fn(ctx, **(args or {}))
    except ToolError as e:
        return f"ERROR: {e}", True
    except TypeError as e:
        return f"ERROR: 工具参数不正确：{e}", True
    except Exception as e:  # noqa: BLE001 - 兜底，绝不中断主循环
        return f"ERROR: {type(e).__name__}: {e}", True

    ok = not result.startswith("ERROR:")
    return result, not ok


__all__ = [
    "ToolContext",
    "ToolError",
    "TOOL_SCHEMAS",
    "FINISH_SENTINEL",
    "dispatch",
]
