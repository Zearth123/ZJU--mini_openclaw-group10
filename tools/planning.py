from contextvars import ContextVar

from agent.planning import TodoList

from .base import Tool


TODO = TodoList()
_ACTIVE_TODO: ContextVar[TodoList] = ContextVar("active_todo", default=TODO)


def current_todo() -> TodoList:
    return _ACTIVE_TODO.get()


def bind_todo(todo: TodoList):
    return _ACTIVE_TODO.set(todo)


def unbind_todo(token) -> None:
    _ACTIVE_TODO.reset(token)


def reset_todo() -> None:
    current_todo().items.clear()


def _todo_write(items: list[str]) -> str:
    todo = current_todo()
    todo.write(items)
    return todo.render()


def _update_todo(id: int, status: str) -> str:
    todo = current_todo()
    todo.update(id, status)
    return todo.render()


todo_write_tool = Tool(
    name="todo_write",
    description="面对多步任务时，先把它分解成有序子任务清单。传入子任务文本数组。",
    parameters={
        "type": "object",
        "properties": {
            "items": {"type": "array", "items": {"type": "string"}, "minItems": 1},
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
                "enum": ["pending", "in_progress", "completed", "blocked"],
            },
        },
        "required": ["id", "status"],
    },
    run=_update_todo,
)
