"""大模型后端：DeepSeek API 客户端（OpenAI 兼容）。

本课程的 mini-OpenClaw 不本地部署模型，而是调用 DeepSeek API 作为"大脑"。
DeepSeek 的接口与 OpenAI 完全兼容，所以下面用通用的 OpenAI 协议写法，
只要改 base_url / api_key / model 就能换任意 OpenAI 兼容厂商。

接口约定（和 FakeBackend 一致，主循环 agent/loop.py 只认这个）：
    chat(messages, tools) -> {"role": "assistant", "content": str, "tool_calls": [ {name, arguments}, ... ]}

环境变量：
    DEEPSEEK_API_KEY   你的 key（千万别提交进 git！）
    DEEPSEEK_BASE_URL  默认 https://api.deepseek.com
    DEEPSEEK_MODEL     默认 deepseek-v4-flash（更强可设 deepseek-v4-pro）
"""
from __future__ import annotations
import os          # 环境变量读取（API Key、Base URL、模型名）
import json        # tool_calls 参数序列化/反序列化
from typing import Any

import httpx      # HTTP 客户端，用于调用 DeepSeek API


# ============================================================
# DeepSeek 后端：封装 OpenAI 兼容的 API 调用
# ============================================================
class DeepSeekBackend:
    def __init__(self,
                 api_key: str | None = None,
                 base_url: str | None = None,
                 model: str | None = None,
                 timeout: float = 180.0):
        # 优先使用传入的参数，否则从环境变量读取
        self.api_key = api_key or os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = (base_url or os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")).rstrip("/")
        # 默认使用 deepseek-v4-flash（更快），可改为 deepseek-v4-pro（更强）
        self.model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
        if not self.api_key:
            raise RuntimeError("缺少 DEEPSEEK_API_KEY 环境变量")
        self._client = httpx.Client(timeout=timeout)

    # 核心方法：非流式对话补全
    # 接收消息列表和工具 schema，返回模型生成的 assistant 消息（含 tool_calls）
    def chat(self, messages: list[dict[str, Any]], tools: list[dict] | None = None,
             temperature: float = 0.0) -> dict[str, Any]:
        """一次（非流式）对话补全，返回归一化的 assistant 消息。"""
        # 构建请求载荷：模型名、消息、温度
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools           # OpenAI tools 格式，base.Tool.schema() 已生成
            payload["tool_choice"] = "auto"    # 让模型自行决定是否调工具

        # 发送 POST 请求到 DeepSeek API
        resp = self._client.post(
            f"{self.base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=payload,
        )
        resp.raise_for_status()                     # 非 2xx 直接抛异常
        body = resp.json()
        msg = body["choices"][0]["message"]          # 取第一个（也是唯一一个）补全结果
        normalized = self._normalize(msg)            # 统一成内部消息格式
        normalized["usage"] = body.get("usage", {})  # 保留 token 用量用于统计
        return normalized

    # --- 内部消息格式 → OpenAI 标准格式 ---
    # 内部使用统一的 {role, content, tool_calls} 格式，
    # OpenAI API 对 tool/assistant 消息有额外的字段要求（tool_call_id, function 等）
    def _to_openai_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for m in messages:
            role = m.get("role")
            if role == "tool":
                # OpenAI 要求 tool 消息带 tool_call_id；内部格式用 name 作为兜底
                out.append({"role": "tool", "content": str(m.get("content", "")),
                            "tool_call_id": m.get("tool_call_id", m.get("name", "tool"))})
            elif role == "assistant" and m.get("tool_calls"):
                # assistant 消息带工具调用时，需要把 tool_calls 转为 API 标准格式
                out.append({"role": "assistant", "content": m.get("content") or None,
                            "tool_calls": self._to_openai_tool_calls(m["tool_calls"])})
            else:
                # user/system 消息：纯文本或多模态 content block
                out.append({"role": role, "content": self._to_openai_content(m.get("content", ""))})
        return out

    @staticmethod
    # 将 Anthropic 风格的图片内容块转换为 OpenAI 兼容的 image_url 格式
    def _to_openai_content(content: Any) -> Any:
        """Translate course/Anthropic image blocks to OpenAI-compatible blocks."""
        if not isinstance(content, list):
            return content               # 非列表（纯文本）直接返回
        blocks = []
        for block in content:
            if block.get("type") != "image":
                blocks.append(block)     # 非图片块（如文本块）原样保留
                continue
            source = block.get("source", {})
            if source.get("type") != "base64":
                raise ValueError("目前只支持 base64 图片内容块")
            media_type = source.get("media_type", "image/png")
            data = source.get("data", "")
            # 转为 data URI 格式：data:image/png;base64,...
            blocks.append({
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{data}"},
            })
        return blocks

    @staticmethod
    # 内部 tool_calls 格式 → OpenAI 函数调用格式（含序列化的 JSON arguments）
    def _to_openai_tool_calls(calls: list[dict]) -> list[dict]:
        out = []
        for i, c in enumerate(calls):
            out.append({"id": c.get("id", f"call_{i}"), "type": "function",
                        "function": {"name": c["name"],
                                     "arguments": json.dumps(c.get("arguments", {}), ensure_ascii=False)}})
        return out

    # --- OpenAI 返回格式 → 内部归一化格式 ---
    # 反向转换：将 OpenAI API 返回的函数调用格式转为内部统一的 {name, arguments} 格式
    @staticmethod
    def _normalize(msg: dict[str, Any]) -> dict[str, Any]:
        tool_calls = []
        for tc in (msg.get("tool_calls") or []):
            fn = tc.get("function", {})
            try:
                args = json.loads(fn.get("arguments") or "{}")   # API 返回的 arguments 是 JSON 字符串，需解析
            except json.JSONDecodeError:
                args = {}                                        # 解析失败时兜底为空字典
            tool_calls.append({"id": tc.get("id"), "name": fn.get("name"), "arguments": args})
        return {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}
