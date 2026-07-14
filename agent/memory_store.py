"""增强记忆系统（与原 memory.py 的 Memory/KVMemory 互补）。

提供持久化键值存储 + 关键词检索 + 系统提示词上下文渲染。
数据存储在 ~/.mini-openclaw/memory/ 下，每条记忆一个 JSON 文件。
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path


MEMORY_DIR = Path.home() / ".mini-openclaw" / "memory"


@dataclass
class MemoryEntry:
    key: str
    value: str
    category: str = "general"
    created_at: float = 0.0
    updated_at: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        now = time.time()
        return {
            "key": self.key,
            "value": self.value,
            "category": self.category,
            "created_at": self.created_at or now,
            "updated_at": now,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict) -> MemoryEntry:
        return cls(
            key=d["key"], value=d["value"], category=d.get("category", "general"),
            created_at=d.get("created_at", 0), updated_at=d.get("updated_at", 0),
            tags=d.get("tags", []),
        )


class MemoryStore:
    """持久化记忆存储，每 key 一个 JSON 文件。"""

    def __init__(self, directory: str | Path = MEMORY_DIR):
        self._dir = Path(directory)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", key)[:64]
        return self._dir / f"{safe}.json"

    def save(self, key: str, value: str, category: str = "general",
             tags: list[str] | None = None) -> MemoryEntry:
        mem = MemoryEntry(key=key, value=value, category=category, tags=tags or [])
        fp = self._path(key)
        if fp.exists():
            mem.created_at = json.loads(fp.read_text()).get("created_at", time.time())
        fp.write_text(json.dumps(mem.to_dict(), ensure_ascii=False, indent=2))
        return mem

    def load(self, key: str) -> MemoryEntry | None:
        fp = self._path(key)
        return MemoryEntry.from_dict(json.loads(fp.read_text())) if fp.exists() else None

    def delete(self, key: str) -> bool:
        fp = self._path(key)
        return fp.unlink() or True if fp.exists() else False

    def list(self, category: str | None = None) -> list[MemoryEntry]:
        memories = []
        for fp in sorted(self._dir.glob("*.json")):
            mem = MemoryEntry.from_dict(json.loads(fp.read_text()))
            if category is None or mem.category == category:
                memories.append(mem)
        return memories

    def recall(self, query: str, max_results: int = 5) -> list[MemoryEntry]:
        query_lower = query.lower()
        words = query_lower.split()
        scored: list[tuple[float, MemoryEntry]] = []
        for mem in self.list():
            score = 0.0
            text = (mem.value + " " + mem.key + " " + " ".join(mem.tags)).lower()
            if query_lower in text:
                score += 3.0
            for w in words:
                if w in text:
                    score += 1.0
                    if w in mem.key.lower():
                        score += 2.0
                    if any(w in t.lower() for t in mem.tags):
                        score += 1.5
            if score > 0:
                scored.append((score, mem))
        scored.sort(key=lambda x: -x[0])
        return [mem for _, mem in scored[:max_results]]

    def to_context(self, max_memories: int = 8) -> str:
        memories = self.list()
        if not memories:
            return ""
        memories.sort(key=lambda m: m.updated_at, reverse=True)
        memories = memories[:max_memories]
        lines = ["## 记忆（跨任务持久上下文）", ""]
        for mem in memories:
            date = time.strftime("%m-%d %H:%M", time.localtime(mem.updated_at))
            lines.append(f"- [{mem.category}] **{mem.key}**（{date}）")
            first_line = mem.value.split("\n")[0].strip()
            if first_line:
                lines.append(f"  {first_line}")
            if mem.tags:
                lines.append(f"  标签: {', '.join(mem.tags)}")
            lines.append("")
        return "\n".join(lines)


_default_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    global _default_store
    if _default_store is None:
        _default_store = MemoryStore()
    return _default_store
