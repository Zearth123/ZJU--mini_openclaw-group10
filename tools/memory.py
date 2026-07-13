from agent.memory import Memory

from .base import Tool


def _remember(note: str) -> str:
    Memory("MEMORY.md").write(note)
    return "已记住：" + note


remember_tool = Tool(
    name="remember",
    description=(
        "当用户告诉你一条应长期记住的项目约定 / 偏好 / 关键决策时，"
        "调用它写入持久记忆。"
    ),
    parameters={
        "type": "object",
        "properties": {"note": {"type": "string"}},
        "required": ["note"],
    },
    run=_remember,
)
