"""上下文管理（Day5）：token 预算、滑动窗口、自动摘要 / compaction。

模型上下文窗口有限。长任务里 messages 会越堆越长，迟早超预算。
策略：
  - 估算当前 messages 的 token 数；
  - 超过阈值时触发 compaction：把较早的对话摘要成一条 system 备忘，
    保留最近 K 轮原文 + 关键工具结果；
  - tool result 过长时先截断/摘要再注入。
"""
from __future__ import annotations
from typing import Any


def estimate_tokens(messages: list[dict[str, Any]]) -> int:
    return sum(len(str(m.get("content", ""))) for m in messages) // 4

def _summarize(backend, chunk: list[dict]) -> str:
    text = "\n".join(f"{m['role']}: {m.get('content','')}" for m in chunk)
    prompt = "把下面的对话历史压缩成要点，保留任务目标、关键发现、已完成步骤：\n" + text
    resp = backend.chat([{"role": "user", "content": prompt}], tools=[])
    return resp.get("content", "")

def maybe_compact(
    messages: list[dict[str, Any]],
    backend: Any,
    budget: int = 6000,
    keep_recent: int = 4,
) -> list[dict[str, Any]]:
    """超预算时压缩较早历史，并保留最近的完整 Agent 轮次。"""
    if estimate_tokens(messages) <= budget:
        return messages

    if len(messages) <= 1:
        return messages

    system_message = messages[0]
    keep_recent = max(0, keep_recent)

    assistant_starts = [
        index
        for index, message in enumerate(messages[1:], start=1)
        if message.get("role") == "assistant"
    ]

    if keep_recent == 0:
        split_at = len(messages)
    elif len(assistant_starts) > keep_recent:
        split_at = assistant_starts[-keep_recent]
    else:
        return messages

    history_chunk = messages[1:split_at]
    recent_messages = messages[split_at:]

    if not history_chunk:
        return messages

    summary = _summarize(backend, history_chunk)

    memo = {
        "role": "system",
        "content": "历史备忘：" + (summary or "[摘要为空]"),
    }

    return [
        system_message,
        memo,
        *recent_messages,
    ]



def truncate_observation(text: str, max_chars: int = 4000) -> str:
    """工具结果过长时截断并提示。"""
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n...[已截断，共 {len(text)} 字符]"
