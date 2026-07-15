"""文件读写工具（Day4：read / write）。"""
from __future__ import annotations  # 延迟求值类型注解，避免循环引用
from pathlib import Path  # 跨平台路径操作

from .base import Tool  # 工具基类
from .external import wrap_external
from agent.output import resolve_artifact_path  # 外部内容安全包装


def _read(path: str, max_bytes: int = 100_000) -> str:
    """读取文本文件，自动添加行号并控制最大读取字节数，超长时截断提示。"""
    # TODO[Day4] 读取文件，超长截断并提示；带行号更利于后续 edit 定位
    resolved_path = resolve_artifact_path(path)
    with open(resolved_path, "r", encoding="utf-8") as f:
        text = f.read(max_bytes + 1)  # 多读 1 字节以判断是否超过上限

    truncated = len(text) > max_bytes  # 判断内容是否被截断
    if truncated:
        text = text[:max_bytes]  # 只保留前 max_bytes 字节

    lines = text.splitlines()  # 按行分割，用于添加行号
    body = "\n".join(f"{i:>6}\t{ln}" for i, ln in enumerate(lines, 1))
    if truncated:
        body += f"\n... [已截断，仅显示前 {max_bytes} 字节]"

    return wrap_external(body or "[空文件]", f"file:{resolved_path.resolve()}")


def _write(path: str, content: str) -> str:
    """将内容写入指定的文件路径，覆盖写入。返回写入的字节数。"""
    # TODO[Day4] 写文件；注意权限层（Day7）后续会拦截工作目录外的写入
    resolved_path = resolve_artifact_path(path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8") as f:
        n = f.write(content)  # n 为实际写入的字节数

    return f"已写入 {n} 字节到 {resolved_path}"


read_tool = Tool(
    name="read",
    description="读取指定路径的文本文件内容。",
    parameters={"type": "object",
                "properties": {"path": {"type": "string", "description": "文件路径"}},
                "required": ["path"]},
    run=_read,
)

write_tool = Tool(
    name="write",
    description="把内容写入指定路径（覆盖）。",
    parameters={"type": "object",
                "properties": {"path": {"type": "string"},
                               "content": {"type": "string"}},
                "required": ["path", "content"]},
    run=_write,
)
