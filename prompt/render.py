"""对话模板渲染器（Day3 的核心交付物）。

目标：把结构化的 messages + tools，渲染成模型真正看到的**一整段文本/token**。
关键认知：模型从不"接收一个 messages 列表"——它只接收一段拼好的字符串，
里面用特殊标记区分角色，工具 schema 也只是被塞进 system 段的普通文本，
模型输出的 <tool_call>{...}</tool_call> 同样只是它学会生成的普通 token。

Day3 你要：
  1. 用 tokenizers 库观察 GLM tokenizer 对这些特殊标记的切分；
  2. 不借助任何 function-calling API，纯字符串拼接实现下面的 render_prompt；
  3. 送入本地模型，手动解析它生成的工具调用。
"""
from __future__ import annotations
from typing import Any  # 类型标注支持
import json  # JSON 序列化工具 schema

# 本期不再单独实现：agent 直接用 DeepSeek 的工具调用 API（见 Day2/Day4）

# 不同模型的对话模板不同（ChatML / Llama / GLM）。这里以 GLM 风格为例占位。
# TODO[optional] 校对你所用模型的真实特殊标记！拼错一个 token，模型行为就会跑偏。
# 角色标记字典：定义各角色在拼接 prompt 时的特殊 token
ROLE_TOKENS = {
    "system": "<|system|>",
    "user": "<|user|>",
    "assistant": "<|assistant|>",
    "tool": "<|observation|>",
}


def render_tools_block(tools: list[dict[str, Any]]) -> str:
    """把 tool schema 列表渲染成放进 system 段的文本说明。

    格式：列出每个工具的名称、描述和参数 schema，并告知模型调用约定。

    参数:
        tools: 工具 schema 列表（OpenAI 格式）

    返回:
        渲染后的文本块，直接拼接到 system 段中
    """
    # TODO[optional] 设计一个清晰的工具说明格式，并约定模型用
    #   <tool_call>{"name": ..., "arguments": {...}}</tool_call> 来调用。
    if not tools:
        return ""
    lines = ["你可以调用以下工具，调用格式：<tool_call>{\"name\": ..., \"arguments\": {...}}</tool_call>"]
    for t in tools:
        f = t["function"]
        lines.append(f"- {f['name']}: {f['description']}  参数schema={json.dumps(f['parameters'], ensure_ascii=False)}")
    return "\n".join(lines)


def render_prompt(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> str:
    """messages + tools -> 一整段送入模型的文本。

    核心认知：模型从不"接收一个 messages 列表"——它只接收一段拼好的字符串，
    里面用特殊标记区分角色，工具 schema 也只是被塞进 system 段的普通文本。

    参数:
        messages: 对话消息列表（每段含 role 和 content）
        tools: 工具 schema 列表（可选），会被渲染进 system 段

    返回:
        拼接好的单段文本，可直接送入模型 tokenizer
    """
    parts: list[str] = []
    # TODO[optional] 把 tools 说明并入 system 段
    # TODO[optional] 逐条 message 用 ROLE_TOKENS 包裹拼接
    # TODO[optional] 末尾以 assistant 起始标记结尾，提示模型开始生成
    raise NotImplementedError("Day3：实现 render_prompt")


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """从模型生成的文本里解析出工具调用（手动解析，不依赖 API）。

    通过正则表达式提取所有 <tool_call>...</tool_call> 标签包裹的 JSON，
    解析出工具名称和参数，返回工具调用列表。

    参数:
        text: 模型输出的原始文本

    返回:
        工具调用列表，每项包含 name 和 arguments 字段
    """
    # TODO[optional] 用正则/状态机提取所有 <tool_call>...</tool_call>，json.loads 出 name/arguments
    raise NotImplementedError("Day3：实现 parse_tool_calls")
