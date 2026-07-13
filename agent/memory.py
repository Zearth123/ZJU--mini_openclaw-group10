import json
from pathlib import Path


class Memory:
    def __init__(self, path="MEMORY.md"):
        self.path = Path(path)

    def write(self, note: str):
        """写入一条记忆（追加落盘 = 持久化）。"""
        with open(self.path, "a", encoding="utf-8") as file:
            file.write("- " + note.strip() + "\n")

    def recall(self, query: str = "") -> str:
        """召回：最简版本 = 读回全部（策略 A）。"""
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""


class KVMemory:
    """可覆盖、可删除的结构化项目记忆。"""

    def __init__(self, path="memory.json"):
        self.path = Path(path)
        self.data = (
            json.loads(self.path.read_text(encoding="utf-8"))
            if self.path.exists()
            else {}
        )

    def _save(self):
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def remember(self, key, value):
        """写入新记忆，或覆盖同 key 的旧记忆。"""
        self.data[key] = value
        self._save()

    def forget(self, key):
        """删除指定 key；key 不存在时保持不变。"""
        self.data.pop(key, None)
        self._save()
