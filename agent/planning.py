"""Long-running task planning and bounded retry helpers."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from typing import Any


TODO_STATUSES = {"pending", "in_progress", "completed", "blocked"}


class TodoList:
    def __init__(self):
        self.items: list[dict[str, Any]] = []

    def write(self, texts: Iterable[str]):
        self.items = [
            {"id": index + 1, "text": text, "status": "pending"}
            for index, text in enumerate(texts)
        ]

    def update(self, id: int, status: str):
        if status not in TODO_STATUSES:
            raise ValueError(f"无效 todo 状态：{status}")
        for item in self.items:
            if item["id"] == id:
                item["status"] = status
                return
        raise ValueError(f"未找到 todo：{id}")

    def insert(self, text: str):
        self.items.append(
            {"id": len(self.items) + 1, "text": text, "status": "pending"}
        )

    def render(self):
        mark = {
            "pending": "[ ]",
            "in_progress": "[~]",
            "completed": "[x]",
            "blocked": "[!]",
        }
        return "\n".join(
            f'{mark[item["status"]]} {item["id"]} {item["text"]}'
            for item in self.items
        )

    def all_done(self):
        return all(item["status"] == "completed" for item in self.items)

    def active_id(self) -> int | None:
        for item in self.items:
            if item["status"] == "in_progress":
                return item["id"]
        return None

    def snapshot(self) -> tuple[tuple[int, str], ...]:
        return tuple((item["id"], item["status"]) for item in self.items)


class TransientError(Exception):
    """A retryable operation failure."""


def with_retry(fn: Callable[[], Any], max_tries: int = 3, base: float = 0.5):
    """Retry transient failures with exponential backoff."""
    for attempt in range(max_tries):
        try:
            return fn()
        except (TransientError, TimeoutError, ConnectionError):
            if attempt + 1 == max_tries:
                return None
            time.sleep(base * 2 ** attempt)
    return None
