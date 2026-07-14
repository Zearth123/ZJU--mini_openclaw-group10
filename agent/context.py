"""上下文管理（Day5）：token 预算、滑动窗口、自动摘要 / compaction。

模型上下文窗口有限。长任务里 messages 会越堆越长，迟早超预算。
策略：
  - 估算当前 messages 的 token 数；
  - 超过阈值时触发 compaction：把较早的对话摘要成一条 system 备忘，
    保留最近 K 轮原文 + 关键工具结果；
  - tool result 过长时先截断/摘要再注入。
"""
from __future__ import annotations
from typing import Any           # 用于类型注解


# 估算消息列表的 token 数：按字符数 / 4 粗略估算
def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages) // 4

# 内部函数：调用后端模型将一段对话历史压缩成摘要
def _summarize(backend, chunk: list[dict]) -> str:
    text = "\n".join(f"{m['role']}: {m.get('content','')}" for m in chunk)
    prompt = "把下面的对话历史压缩成要点，保留任务目标、关键发现、已完成步骤：\n" + text
    resp = backend.chat([{"role": "user", "content": prompt}], tools=[])
    return resp.get("content", "")

# 核心压缩函数：当消息列表超过 token 预算时，对较早对话进行摘要压缩
def maybe_compact(
    messages: list[dict[str, Any]],
    backend: Any,
    budget: int = 12000,
    keep_recent: int = 8,
) -> list[dict[str, Any]]:
    """超预算时压缩较早历史，并保留最近的完整 Agent 轮次。"""
    if estimate_tokens(messages) <= budget:
        return messages

    if len(messages) <= 1:
        return messages

    system_message = messages[0]   # 保留系统提示词不动
    keep_recent = max(0, keep_recent)

    # 找到所有 assistant（模型回复）消息的索引位置
    assistant_starts = [
        index
        for index, message in enumerate(messages[1:], start=1)
        if message.get("role") == "assistant"
    ]

    # 决定截断点：保留最近 keep_recent 轮 assistant 消息
    if keep_recent == 0:
        split_at = len(messages)
    elif len(assistant_starts) > keep_recent:
        split_at = assistant_starts[-keep_recent]
    else:
        return messages

    history_chunk = messages[1:split_at]    # 待压缩的较早历史
    recent_messages = messages[split_at:]   # 保留的最近消息

    if not history_chunk:
        return messages

    summary = _summarize(backend, history_chunk)  # 调用模型压缩

    # 构建压缩后的备忘消息
    memo = {
        "role": "system",
        "content": "历史备忘：" + (summary or "[摘要为空]"),
    }

    return [
        system_message,
        memo,
        *recent_messages,
    ]



# 截断过长的工具返回结果，防止超出上下文窗口
def truncate_observation(text: str, max_chars: int = 4000) -> str:
    """工具结果过长时截断并提示。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[已截断，共 {len(text)} 字符]"
