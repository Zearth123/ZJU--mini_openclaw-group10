from backend.client import DeepSeekBackend  # 导入 DeepSeek API 客户端，用于与大模型通信

# 定义一个简单的工具 schema：获取当前时间（OpenAI 格式）
tools = [{
    "type": "function",
    "function": {
        "name": "get_time",
        "description": "返回当前时间。用户询问现在几点、当前时间时使用。",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
}]

# 初始化 DeepSeek 后端，发送无 system prompt 的测试请求
backend = DeepSeekBackend()
resp = backend.chat(
    [{"role": "user", "content": "现在几点？"}],
    tools=tools,
)
print(resp)

# 导入系统提示词模板，测试带 system prompt 的请求效果
from agent.prompts import SYSTEM_PROMPT

resp2 = backend.chat(
    [{"role": "system", "content": SYSTEM_PROMPT},
     {"role": "user", "content": "现在几点？"}],
    tools=tools,
)
print(resp2)