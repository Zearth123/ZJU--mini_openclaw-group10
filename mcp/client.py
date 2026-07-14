"""最小 MCP 客户端（Day6/8）。

通过 stdio 与 MCP server 通信，做 JSON-RPC。
支持 initialize 握手、tools/list、tools/call、超时保护。
"""
from __future__ import annotations
import json
import os
import select
import subprocess
import time
from typing import Any

from tools.base import Tool, ToolRegistry


class MCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None):
        self.command = command
        self.env = env
        self.proc: subprocess.Popen | None = None
        self._id = 0

    def start(self) -> None:
        """启动子进程，stdin/stdout 接管，做 initialize 握手"""
        env = os.environ.copy()
        if self.env:
            env.update(self.env)
        self.proc = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "mini-openclaw", "version": "0.1"},
        })
        self._send({
            "jsonrpc": "2.0", "method": "notifications/initialized",
        })

    def _send(self, req: dict) -> None:
        assert self.proc is not None and self.proc.stdin is not None
        self.proc.stdin.write(json.dumps(req) + "\n")
        self.proc.stdin.flush()

    def _rpc(self, method: str, params: dict | None = None, timeout: float = 30.0) -> Any:
        self._id += 1
        req = {"jsonrpc": "2.0", "id": self._id, "method": method}
        if params is not None:
            req["params"] = params
        self._send(req)
        assert self.proc is not None and self.proc.stdout is not None
        deadline = time.monotonic() + timeout
        line = ""
        while time.monotonic() < deadline:
            r, _, _ = select.select([self.proc.stdout], [], [], 0.5)
            if r:
                line = self.proc.stdout.readline()
                break
        if not line:
            raise RuntimeError(f"MCP 请求 {method} 超时（{timeout}s）")
        resp = json.loads(line)
        if "error" in resp:
            raise RuntimeError(f"MCP 调用失败 [{method}]: {resp['error']['message']}")
        return resp.get("result")

    def list_tools(self) -> list[dict]:
        result = self._rpc("tools/list")
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> str:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content", [])
        texts = [item["text"] for item in content if item.get("type") == "text"]
        return "\n".join(texts)

    def stop(self) -> None:
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)
            self.proc = None


def register_mcp_tools(registry: ToolRegistry, client: MCPClient) -> None:
    for spec in client.list_tools():
        name = spec["name"]
        registry.register(Tool(
            name=f"mcp__{name}",
            description=spec.get("description", ""),
            parameters=spec.get("inputSchema", {"type": "object", "properties": {}}),
            run=lambda _n=name, **kw: client.call_tool(_n, kw),
        ))
