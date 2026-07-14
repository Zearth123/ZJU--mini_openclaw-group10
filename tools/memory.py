"""长期记忆写入工具（Day 7）。"""
from __future__ import annotations

from agent.memory import Memory
from .base import Tool


def _remember(note: str) -> str:
    """把一条长期有效的信息追加到 MEMORY.md。"""
    note = note.strip()
    if not note:
        return "[失败] 记忆内容不能为空"

    Memory("MEMORY.md").write(note)
    return "已记住：" + note


remember_tool = Tool(
    name="remember",
    description=(
        "当用户明确告诉你一条应跨会话长期保存的项目约定、"
        "用户偏好或关键决策时，调用此工具写入持久记忆。"
        "不要保存临时任务状态、未经确认的推测、密码、API Key 或其他敏感信息。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "note": {
                "type": "string",
                "description": "需要长期保存的一条简洁、明确的信息",
            },
        },
        "required": ["note"],
    },
    run=_remember,
)