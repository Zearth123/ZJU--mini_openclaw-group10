from agent.memory import KVMemory, Memory
from tools.memory import _remember


def test_memory_persists_across_instances(tmp_path):
    path = tmp_path / "MEMORY.md"

    Memory(path).write("项目使用 Python 3.11")

    assert Memory(path).recall() == "- 项目使用 Python 3.11\n"


def test_recall_returns_empty_when_file_does_not_exist(tmp_path):
    assert Memory(tmp_path / "MEMORY.md").recall() == ""


def test_kv_memory_can_update_and_forget(tmp_path):
    path = tmp_path / "memory.json"
    memory = KVMemory(path)

    memory.remember("pm", "npm")
    memory.remember("pm", "pnpm")
    memory.remember("temporary", True)
    memory.forget("temporary")

    assert KVMemory(path).data == {"pm": "pnpm"}


def test_remember_tool_writes_project_memory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = _remember("API 时间戳使用 ISO-8601")

    assert result == "已记住：API 时间戳使用 ISO-8601"
    assert Memory("MEMORY.md").recall() == "- API 时间戳使用 ISO-8601\n"
