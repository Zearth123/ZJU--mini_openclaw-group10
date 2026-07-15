from agent.loop import AgentLoop, TODO_HEADING
from agent.planning import TodoList
from tools.base import build_default_registry
from tools.planning import TODO


class ScriptedBackend:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.seen_messages = []
        self.seen_tools = []

    def chat(self, messages, tools):
        self.seen_messages.append([dict(message) for message in messages])
        self.seen_tools.append(tools)
        return next(self.responses)


def tool_call(name, arguments):
    return {"content": "", "tool_calls": [{"name": name, "arguments": arguments}]}


def test_todo_list_state_machine():
    todo = TodoList()
    todo.write(["A", "B"])
    todo.update(1, "completed")
    todo.insert("C")

    assert todo.render() == "[x] 1 A\n[ ] 2 B\n[ ] 3 C"
    assert not todo.all_done()


def test_loop_keeps_todo_visible_but_allows_optional_early_finish(tmp_path):
    backend = ScriptedBackend([
        tool_call("todo_write", {"items": ["A"]}),
        tool_call("update_todo", {"id": 1, "status": "in_progress"}),
        {"content": "done", "tool_calls": []},
    ])
    loop = AgentLoop(
        backend,
        build_default_registry(),
        "system",
        workdir=tmp_path,
    )

    assert loop.run("multi-step task") == "done"
    assert any(
        message.get("role") == "system"
        and message.get("content", "").startswith(TODO_HEADING)
        for message in backend.seen_messages[1]
    )
    assert not TODO.all_done()


def test_multistep_task_does_not_require_todo_before_other_tools(tmp_path):
    backend = ScriptedBackend([
        {"content": "done", "tool_calls": []},
    ])
    loop = AgentLoop(backend, build_default_registry(), "system", workdir=tmp_path)

    assert loop.run("迁移所有调用并运行测试") == "done"
    first_tool_names = {
        schema["function"]["name"] for schema in backend.seen_tools[0]
    }
    assert "todo_write" in first_tool_names
    assert "calculate_budget" in first_tool_names


def test_bounded_stop_emits_terminal_event(tmp_path):
    backend = ScriptedBackend([tool_call("missing", {})])
    events = []
    loop = AgentLoop(
        backend, build_default_registry(), "system", max_turns=1,
        workdir=tmp_path,
        event_callback=lambda kind, data: events.append((kind, data)),
    )
    assert loop.run("bounded task")
    assert events[-1][0] == "run_finished"
    assert events[-1][1]["limited"] is True


def test_loop_has_bounded_stop(tmp_path):
    backend = ScriptedBackend([
        tool_call("missing", {}),
        tool_call("missing", {}),
        tool_call("missing", {}),
        tool_call("missing", {}),
    ])
    loop = AgentLoop(
        backend,
        build_default_registry(),
        "system",
        max_turns=4,
        workdir=tmp_path,
    )

    result = loop.run("multi-step task")

    assert "已达步数上限" in result


def test_verbose_mode_prints_todo_tool_calls(tmp_path, capsys):
    backend = ScriptedBackend([
        tool_call("todo_write", {"items": ["A"]}),
        tool_call("update_todo", {"id": 1, "status": "completed"}),
        {"content": "done", "tool_calls": []},
    ])
    loop = AgentLoop(
        backend,
        build_default_registry(),
        "system",
        workdir=tmp_path,
        verbose=True,
    )

    assert loop.run("multi-step task") == "done"
    stderr = capsys.readouterr().err
    assert "[tool] todo_write" in stderr
    assert "[tool] update_todo" in stderr
    assert "[x] 1 A" in stderr


def test_loop_includes_conversation_history(tmp_path):
    backend = ScriptedBackend([{"content": "continued", "tool_calls": []}])
    loop = AgentLoop(backend, build_default_registry(), "system", workdir=tmp_path)

    assert loop.run(
        "按通用场景来设计",
        history_messages=[
            {"role": "user", "content": "设计书画社活动，40人，预算1000元"},
            {"role": "assistant", "content": "请确认场地"},
        ],
    ) == "continued"

    seen = backend.seen_messages[0]
    assert [message["role"] for message in seen[:4]] == [
        "system", "user", "assistant", "user",
    ]
    assert "40人" in seen[1]["content"]
    assert seen[3]["content"] == "按通用场景来设计"
