from agent.planning import TodoList

from .base import Tool


TODO = TodoList()


def reset_todo() -> None:
    TODO.items.clear()


def _todo_write(items: list[str]) -> str:
    TODO.write(items)
    return TODO.render()


def _update_todo(id: int, status: str) -> str:
    TODO.update(id, status)
    return TODO.render()


todo_write_tool = Tool(
    name="todo_write",
    description="面对多步任务时，先把它分解成有序子任务清单。传入子任务文本数组。",
    parameters={
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["items"],
    },
    run=_todo_write,
)


update_todo_tool = Tool(
    name="update_todo",
    description="开始、完成或阻塞某条子任务时更新其状态。",
    parameters={
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "status": {
                "type": "string",
                "enum": ["in_progress", "completed", "blocked"],
            },
        },
        "required": ["id", "status"],
    },
    run=_update_todo,
)
