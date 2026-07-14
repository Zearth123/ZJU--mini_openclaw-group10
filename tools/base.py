"""工具抽象与注册表。

核心思想（贯穿全课）：
  「工具」就是一个有 name / description / 输入 schema / run() 的对象。
  模型并不会"真的调用函数"——它只是生成一段文本
  <tool_call>{"name": ..., "arguments": {...}}</tool_call>，
  由主循环（agent/loop.py）解析出来，找到同名 Tool，执行它的 run()，
  再把返回值作为 observation 喂回模型。

Day4 实现 read/write/bash 与 edit/grep/glob；Day5 补 web_fetch/task_list。
"""
from __future__ import annotations  # 确保类型注解在运行时不会执行
from dataclasses import dataclass, field  # 数据类，用于简化 Tool/ToolRegistry 定义
from typing import Any, Callable  # 类型提示：Any 任意类型，Callable 可调用对象


@dataclass
class Tool:
    """单个工具的抽象表示。包含名称、描述、输入参数的 JSON Schema 以及可调用执行体。"""
    name: str  # 工具名称，模型通过 name 来引用该工具
    description: str  # 工具用途描述，会传给模型帮助其理解何时调用
    # JSON Schema（OpenAI tools 格式里的 parameters）。它最终会变成 API 的 tools 字段 / prompt 里的文本。
    parameters: dict[str, Any]
    run: Callable[..., str]   # run(**arguments) -> str（observation 文本）

    def schema(self) -> dict[str, Any]:
        """转成 OpenAI tools 格式的完整描述项，供 API 的 tools 参数使用。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolRegistry:
    """工具注册表，管理所有可用工具的注册、查询和 schema 生成。"""
    _tools: dict[str, Tool] = field(default_factory=dict)  # 内部存储结构：name -> Tool

    def register(self, tool: Tool) -> None:
        """注册一个新工具；重名时抛出 ValueError 防止覆盖。"""
        if tool.name in self._tools:
            raise ValueError(f"工具重名：{tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        """按名称查找已注册的工具，未找到时返回 None。"""
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        """返回所有已注册工具的 OpenAI-compatible schema 列表。"""
        return [t.schema() for t in self._tools.values()]

    def names(self) -> list[str]:
        """返回所有已注册工具的名称列表。"""
        return list(self._tools)

    def __len__(self) -> int:
        """返回已注册工具的数量。"""
        return len(self._tools)


def build_default_registry() -> ToolRegistry:
    """组装 mini-OpenClaw 的所有内置工具，返回一个完整的 ToolRegistry 实例。"""
    reg = ToolRegistry()  # 创建一个空注册表

    # 通用文件与执行工具：文件读写、shell 执行、编辑、搜索和网络抓取
    from .fs import read_tool, write_tool
    from .shell import bash_tool
    from .more_tools import (
        edit_tool,
        grep_tool,
        glob_tool,
        web_fetch_tool,
    )

    # 记忆工具：跨会话持久化用户偏好和约定
    from .memory import remember_tool

    # Todo 规划工具：任务分解、状态跟踪
    from .planning import todo_write_tool, update_todo_tool

    # 活动策划确定性工具：预算计算、排期生成、合规校验
    from .activity_budget import calculate_budget_tool
    from .activity_schedule import build_schedule_tool
    from .activity_validate import validate_project_tool

    tools = [  # 所有内置工具的有序列表
        read_tool,
        write_tool,
        bash_tool,
        edit_tool,
        grep_tool,
        glob_tool,
        web_fetch_tool,
        remember_tool,
        todo_write_tool,
        update_todo_tool,
        calculate_budget_tool,
        build_schedule_tool,
        validate_project_tool,
    ]

    for tool in tools:  # 依次注册每个工具到注册表中
        reg.register(tool)

    return reg
