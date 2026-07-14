"""Todo 规划工具：连接 AgentLoop 与 agent.planning.TodoList。"""

from __future__ import annotations

from agent.planning import TodoList

from .base import Tool


TODO = TodoList()


def reset_todo() -> None:
    """开始新任务前清空上一次会话的 Todo。"""
    TODO.items.clear()


def _write_todo(items: list[str]) -> str:
    TODO.write(items)
    return TODO.render()


def _update_todo(id: int, status: str) -> str:
    TODO.update(id, status)
    return TODO.render()


todo_write_tool = Tool(
    name="todo_write",
    description="将复杂任务分解为有序的子任务清单。",
    parameters={
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
            },
        },
        "required": ["items"],
    },
    run=_write_todo,
)


update_todo_tool = Tool(
    name="update_todo",
    description="更新指定 Todo 的执行状态。",
    parameters={
        "type": "object",
        "properties": {
            "id": {
                "type": "integer",
                "minimum": 1,
            },
            "status": {
                "type": "string",
                "enum": [
                    "pending",
                    "in_progress",
                    "completed",
                    "blocked",
                ],
            },
        },
        "required": ["id", "status"],
    },
    run=_update_todo,
)