"""Todo 规划工具：连接 AgentLoop 与 agent.planning.TodoList。"""

from __future__ import annotations  # 延迟求值类型注解

from agent.planning import TodoList  # 待办清单管理器，负责任务分解和状态跟踪

from .base import Tool  # 工具基类


TODO = TodoList()  # 全局单例的 Todo 清单实例，供 AgentLoop 在任务之间重用


def reset_todo() -> None:
    """清空 Todo 清单，用于开始新任务前重置状态。"""
    TODO.items.clear()


def _write_todo(items: list[str]) -> str:
    """写入新的 Todo 清单（覆盖旧清单），返回格式化后的待办列表。"""
    TODO.write(items)
    return TODO.render()  # 返回美化后的待办文本


def _update_todo(id: int, status: str) -> str:
    """更新指定序号（从 1 开始）的 Todo 项的状态，返回更新后的清单。"""
    TODO.update(id, status)
    return TODO.render()


# 创建任务分解清单的工具注册
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

# 更新已创建任务状态的工具注册
update_todo_tool = Tool(
    name="update_todo",
    description="更新指定 Todo 的执行状态（pending/in_progress/completed/blocked）。",
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
                    "pending",       # 待处理
                    "in_progress",   # 进行中
                    "completed",     # 已完成
                    "blocked",       # 被阻塞
                ],
            },
        },
        "required": ["id", "status"],
    },
    run=_update_todo,
)