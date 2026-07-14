"""一个最小 MCP server（自写 echo），用于 Day8 先打通握手再接官方 server。

只暴露一个工具 echo(text)，原样返回。用 stdio + JSON-RPC。
跑通这个，再去接官方 filesystem server。

注意：这是给 client 连的"对端"，本身就是个最小 JSON-RPC 循环。
"""
from __future__ import annotations
import json  # JSON-RPC 消息的解析和生成
import sys  # 标准输入输出，实现 stdio 传输层

# MCP server 暴露的唯一工具：echo，原样返回输入的文本
TOOLS = [{
    "name": "echo",
    "description": "原样返回输入的 text。",
    "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
}]


def handle(req: dict) -> dict | None:
    """处理一条 JSON-RPC 请求，根据方法名分发到对应逻辑。

    支持的方法：
        - initialize: MCP 握手初始化
        - tools/list: 返回可用工具列表
        - tools/call: 执行工具调用（echo）
        - 其他：返回 method not found 错误

    参数:
        req: 解析后的 JSON-RPC 请求字典

    返回:
        响应字典，通知类请求（无 id）返回 None
    """
    method = req.get("method")
    rid = req.get("id")
    # initialize 握手：返回协议版本、服务信息和能力声明
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"protocolVersion": "2024-11-05",
                           "serverInfo": {"name": "echo", "version": "0.1"},
                           "capabilities": {"tools": {}}}}
    # tools/list：返回 server 暴露的工具列表
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}
    # tools/call：执行 echo 工具，原样返回 text 参数
    if method == "tools/call":
        text = req["params"]["arguments"].get("text", "")
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": text}]}}
    # 通知类请求（如 notifications/initialized）无需回应
    if rid is None:
        return None
    # 未知方法返回标准 JSON-RPC 错误码 -32601
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}


def main() -> None:
    """MCP server 主循环：从 stdin 逐行读取 JSON-RPC 请求，处理后写入 stdout。

    这是一个典型的 stdio 传输层实现：
        1. 从 stdin 读取一行 JSON
        2. 调用 handle 处理请求
        3. 将响应写入 stdout（flush 确保立即发送）
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:  # 跳过空行
            continue
        resp = handle(json.loads(line))  # 解析 JSON 并处理
        if resp is not None:  # 通知类请求无需回复
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()  # 立即刷新，确保 client 能收到


if __name__ == "__main__":
    main()
