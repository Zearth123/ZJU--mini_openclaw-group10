"""一个"假后端"，用于未配 DeepSeek key 时离线跑通骨架。

它实现和真后端 backend/client.py（DeepSeekBackend）一样的最小接口：
  chat(messages, tools) -> {"role": "assistant", "content": ..., "tool_calls": [...] }

行为：用极简规则模拟一个会调用工具的模型，让 selfcheck / 主循环骨架能跑。
配好 DEEPSEEK_API_KEY 后，agent/cli.py 会自动改用真模型（DeepSeekBackend）。
"""
from __future__ import annotations
from typing import Any


# ============================================================
# 假后端：未配置 API Key 时的离线占位实现
# 与 DeepSeekBackend 实现相同的 chat() 接口，方便切换
# ============================================================
class FakeBackend:
    """规则驱动的假模型：只为打通管道，不要当真。"""

    # 模拟 chat 接口：根据最后一条消息内容做简单规则判断
    def chat(self, messages: list[dict[str, Any]], tools: list[dict] | None = None) -> dict[str, Any]:
        last = messages[-1]["content"] if messages else ""
        last_text = self._text_content(last)
        # 规则1：如果上一条是工具结果（observation），就假装给出最终答复
        if messages and messages[-1].get("role") == "tool":
            return {"role": "assistant", "content": f"[FakeBackend] 已根据工具结果完成：{last_text[:60]}", "tool_calls": []}

        # 规则2：如果有可用工具且用户输入含关键词，假装调用第一个工具
        if tools and any(k in last_text for k in ("文件", "运行", "file", "run", "hello")):
            name = tools[0]["function"]["name"]
            return {
                "role": "assistant",
                "content": "",                                          # 空 content 表示模型"正在调用工具"
                "tool_calls": [{"name": name, "arguments": {}}],       # 假装调用工具（参数为空）
            }
        # 规则3：兜底——发回一条欢迎/提示消息
        return {"role": "assistant", "content": "[FakeBackend] 你好，我是离线占位后端。配好 DEEPSEEK_API_KEY 即用真模型。", "tool_calls": []}

    @staticmethod
    def _text_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(
                str(block.get("text", ""))
                for block in content
                if isinstance(block, dict) and block.get("type") == "text"
            )
        return str(content)
