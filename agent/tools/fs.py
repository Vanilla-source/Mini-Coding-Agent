"""文件类工具：list_dir / read_file / write_file / replace_in_file。

统一约束：所有路径解析后必须落在本次运行的 workspace 之内，防止模型越界读写。
"""

from __future__ import annotations

from pathlib import Path

from . import ToolContext, ToolError

MAX_READ_BYTES = 200_000   # 单次读取上限，超出提示模型分段读
MAX_LIST_ENTRIES = 200


def resolve_path(ctx: ToolContext, path: str | Path) -> Path:
    """把用户给的路径解析到 workspace 内，越界则抛 ToolError。"""
    root = Path(ctx.workspace).resolve()
    raw = Path(path)
    target = (root / raw).resolve() if not raw.is_absolute() else raw.resolve()

    if target != root and root not in target.parents:
        raise ToolError(f"路径越界：{path!r} 不在工作目录 {root} 内")
    return target


def _rel(ctx: ToolContext, p: Path) -> str:
    try:
        return str(p.relative_to(Path(ctx.workspace).resolve()))
    except ValueError:
        return str(p)


# ---------------------------------------------------------------- list_dir

def list_dir(ctx: ToolContext, path: str = ".") -> str:
    target = resolve_path(ctx, path)
    if not target.exists():
        return f"ERROR: 目录不存在：{path}"

    if target.is_file():
        return f"{path} 是一个文件，大小 {target.stat().st_size} 字节"

    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    if not entries:
        return f"目录 {path} 是空的。"

    lines = []
    for p in entries[:MAX_LIST_ENTRIES]:
        if p.is_dir():
            lines.append(f"[dir ] {p.name}/")
        else:
            lines.append(f"[file] {p.name}  ({p.stat().st_size} B)")
    if len(entries) > MAX_LIST_ENTRIES:
        lines.append(f"... 还有 {len(entries) - MAX_LIST_ENTRIES} 项未显示")

    return f"{path} 下共 {len(entries)} 项：\n" + "\n".join(lines)


# --------------------------------------------------------------- read_file

def read_file(ctx: ToolContext, path: str, start_line: int = 1,
              end_line: int = 0) -> str:
    target = resolve_path(ctx, path)
    if not target.exists():
        return f"ERROR: 文件不存在：{path}"
    if target.is_dir():
        return f"ERROR: {path} 是目录，不是文件。先用 list_dir 看看里面有什么。"

    size = target.stat().st_size
    try:
        text = target.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # noqa: BLE001
        return f"ERROR: 读取失败 {path}：{e}"

    lines = text.splitlines()
    total = len(lines)
    start = max(1, int(start_line or 1))
    end = int(end_line or 0) or total
    if start > total:
        return f"ERROR: start_line={start} 超出文件总行数 {total}"
    end = min(max(end, start), total)

    shown = lines[start - 1:end]
    if size > MAX_READ_BYTES:
        shown = shown[:400]
        end = start + len(shown) - 1

    width = len(str(end))
    body = "\n".join(f"{i:>{width}} | {line}" for i, line in enumerate(shown, start))
    header = f"{path}（共 {total} 行，显示 {start}-{end} 行）"
    if end < total:
        header += f"\n[还有 {total - end} 行未显示，用 start_line={end + 1} 继续读]"
    return f"{header}\n{body}"


# -------------------------------------------------------------- write_file

def write_file(ctx: ToolContext, path: str, content: str) -> str:
    target = resolve_path(ctx, path)
    if target.is_dir():
        return f"ERROR: {path} 是目录，不能直接写入。"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    n_lines = content.count("\n") + (1 if content and not content.endswith("\n") else 0)
    return f"已写入 {_rel(ctx, target)}（{n_lines} 行，{len(content)} 字符）"


# ---------------------------------------------------------- replace_in_file

def replace_in_file(ctx: ToolContext, path: str, old_string: str,
                    new_string: str) -> str:
    target = resolve_path(ctx, path)
    if not target.exists():
        return f"ERROR: 文件不存在：{path}。新建文件请用 write_file。"

    text = target.read_text(encoding="utf-8")
    occurrences = text.count(old_string)

    if occurrences == 0:
        return ("ERROR: 在文件中找不到 old_string（必须与原文完全一致，包括空格与缩进）。"
                "建议先用 read_file 查看原文。")
    if occurrences > 1:
        return (f"ERROR: old_string 在文件中出现了 {occurrences} 次，无法确定替换哪一处。"
                "请提供更长、更唯一的上下文片段。")

    target.write_text(text.replace(old_string, new_string, 1),
                      encoding="utf-8", newline="\n")
    return f"已替换 {_rel(ctx, target)} 中的 1 处（{len(old_string)} -> {len(new_string)} 字符）"
