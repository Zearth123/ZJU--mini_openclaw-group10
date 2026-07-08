from __future__ import annotations
import json, re
from typing import Any

TOOL_CALL_FULL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
TOOL_CALL_TRUNC_RE = re.compile(r"<tool_call>\s*(\{[\s\S]*)")

# 一条记录 = 一次任务运行留下的轨迹。steps 里每步含：模型这步请求的
# tool_calls、原始文本 raw（含 <tool_call>）、以及该步的 token 计数。
SAMPLE_RECORDS: list[dict[str, Any]] = [
    {"task": "read-config",
     "steps": [
         {"tool_calls": [{"name": "read", "arguments": {"path": "config.json"}}],
          "raw": '<tool_call>{"name":"read","arguments":{"path":"config.json"}}</tool_call>',
          "prompt_tokens": 310, "completion_tokens": 22},
     ],
     "final": "config.json 里 timeout = 30 秒。"},
    {"task": "list-dir",
     "steps": [
         {"tool_calls": [{"name": "bash", "arguments": {"command": "ls"}}],
          "raw": '<tool_call>{"name":"bash","arguments":{"command":"ls"}}</tool_call>',
          "prompt_tokens": 290, "completion_tokens": 18},
     ],
     "final": "当前目录有：main.py config.json README.md"},
    {"task": "read-config",          # 一条“失败/低质量”样本：JSON 被截断，且没报出值
     "steps": [
         {"tool_calls": [],
          "raw": '<tool_call>{"name":"read","arguments":{"path":',   # 坏 JSON
          "prompt_tokens": 305, "completion_tokens": 12},
         {"tool_calls": [], "raw": "我不确定 timeout 的值。",
          "prompt_tokens": 340, "completion_tokens": 15},
     ],
     "final": "我不确定 timeout 的值。"},
]

def success_rate(tasks: list, records: list[dict]) -> float:
    """对每条 (task, trajectory) 记录跑 task.check，返回成功比例。"""
    by_name = {t.name: t for t in tasks}
    ok = 0
    for r in records:
        task = by_name.get(r["task"])
        if task and task.check(r):      # 复用步骤 1 的成功判据
            ok += 1
    return ok / max(len(records), 1)

def step_count(record: dict) -> int:
    return len(record["steps"])

def token_count(record: dict) -> int:
    return sum(s.get("prompt_tokens", 0) + s.get("completion_tokens", 0)
               for s in record["steps"])

def json_valid_rate(records: list[dict]) -> float:
    """扫每步 raw 里的 <tool_call>，提取 JSON 并校验；坏 JSON 计入分母不计入分子。"""
    total, ok = 0, 0
    for r in records:
        for s in r["steps"]:
            m = TOOL_CALL_FULL_RE.search(s.get("raw", ""))
            if not m:
                m = TOOL_CALL_TRUNC_RE.search(s.get("raw", ""))
            if not m:
                continue
            total += 1
            try:
                json.loads(m.group(1))
                ok += 1
            except json.JSONDecodeError:
                pass
    return ok / max(total, 1)

if __name__ == "__main__":
    from eval.tasks import SAMPLE_TASKS
    recs = SAMPLE_RECORDS
    print("成功率        :", success_rate(SAMPLE_TASKS, recs))
    print("平均步数      :", sum(step_count(r) for r in recs) / len(recs))
    print("平均 token    :", sum(token_count(r) for r in recs) / len(recs))
    print("JSON 合法率   :", json_valid_rate(recs))