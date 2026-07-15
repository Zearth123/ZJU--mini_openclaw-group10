"""长期记忆写入工具（Day 7）。"""
from __future__ import annotations  # 延迟求值类型注解

from agent.memory import Memory  # 持久化记忆管理器
from .base import Tool  # 工具基类


def _remember(note: str) -> str:
    """将用户指定的长期记忆写入 MEMORY.md 文件，供跨会话持久化使用。"""
    note = note.strip()
    if not note:
        return "[失败] 记忆内容不能为空"

    Memory("MEMORY.md").write(note)  # 追加写入到 MEMORY.md
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