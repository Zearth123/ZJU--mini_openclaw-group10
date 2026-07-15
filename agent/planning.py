"""长任务规划与有限重试辅助工具。

提供任务清单（TodoList）管理和带指数退避的重试机制（with_retry）。
"""

from __future__ import annotations

import time                     # 指数退避等待
from collections.abc import Callable, Iterable  # 函数式编程类型
from typing import Any          # 通用类型注解


# 任务项的四种状态
TODO_STATUSES = {"pending", "in_progress", "completed", "blocked"}


class TodoList:
    """任务清单：管理待办事项的新建、更新、渲染和状态追踪。"""

    def __init__(self):
        self.items: list[dict[str, Any]] = []

    def write(self, texts: Iterable[str]):
        """用一组文本批量替换当前任务清单，全部初始化为 pending 状态。"""
        self.items = [
            {"id": index + 1, "text": text, "status": "pending"}
            for index, text in enumerate(texts)
        ]

    def update(self, id: int, status: str):
        """更新指定 id 的任务状态（pending / in_progress / completed / blocked）。"""
        if status not in TODO_STATUSES:
            raise ValueError(f"无效 todo 状态：{status}")
        for item in self.items:
            if item["id"] == id:
                item["status"] = status
                return
        raise ValueError(f"未找到 todo：{id}")

    def insert(self, text: str):
        """在清单末尾插入一条新任务。"""
        self.items.append(
            {"id": len(self.items) + 1, "text": text, "status": "pending"}
        )

    def render(self):
        """渲染清单为可读文本格式：[ ] 待办 / [~] 进行中 / [x] 完成 / [!] 阻塞。"""
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
        """检查是否所有任务均已完成。"""
        return all(item["status"] == "completed" for item in self.items)

    def active_id(self) -> int | None:
        """返回当前进行中的任务 id，若无则返回 None。"""
        for item in self.items:
            if item["status"] == "in_progress":
                return item["id"]
        return None

    def snapshot(self) -> tuple[tuple[int, str], ...]:
        """返回当前任务状态的快照（用于检测本轮是否有进展变化）。"""
        return tuple((item["id"], item["status"]) for item in self.items)


class TransientError(Exception):
    """可重试的临时错误异常（区别于永久性失败）。"""


def with_retry(fn: Callable[[], Any], max_tries: int = 3, base: float = 0.5):
    """带指数退避的重试包装器：对瞬时错误最多重试 max_tries 次。"""
    for attempt in range(max_tries):
        try:
            return fn()
        except (TransientError, TimeoutError, ConnectionError):
            if attempt + 1 == max_tries:
                return None          # 最后一次失败，返回 None 表示失败
            time.sleep(base * 2 ** attempt)  # 指数退避等待
    return None
