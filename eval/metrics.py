from __future__ import annotations
import json, re  # json：解析工具调用数据；re：正则匹配 <tool_call> 标签
from typing import Any

# 匹配完整 <tool_call> 包裹的 JSON 内容
TOOL_CALL_FULL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
# 匹配被截断的 <tool_call>（缺少结束标签），用于容错解析
TOOL_CALL_TRUNC_RE = re.compile(r"<tool_call>\s*(\{[\s\S]*)")

# 一条记录 = 一次任务运行留下的轨迹。steps 里每步含：模型这步请求的
# tool_calls、原始文本 raw（含 <tool_call>）、以及该步的 token 计数。
# 三条样本：两条成功（read-config、list-dir），一条失败（read-config 被截断）
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
    """对每条 (task, trajectory) 记录跑 task.check，返回成功比例。

    参数:
        tasks: 任务定义列表，每个任务有 name 和 check 方法
        records: 轨迹记录列表

    返回:
        float: 成功记录占比（0.0 ~ 1.0）
    """
    by_name = {t.name: t for t in tasks}  # 按任务名建立索引，加速查找
    ok = 0
    for r in records:
        task = by_name.get(r["task"])
        if task and task.check(r):      # 复用步骤 1 的成功判据
            ok += 1
    return ok / max(len(records), 1)  # 避免除以零

def step_count(record: dict) -> int:
    """返回一条轨迹中的步骤总数。"""
    return len(record["steps"])

def token_count(record: dict) -> int:
    """统计一条轨迹消耗的 token 总数（prompt + completion）。"""
    return sum(s.get("prompt_tokens", 0) + s.get("completion_tokens", 0)
               for s in record["steps"])

def json_valid_rate(records: list[dict]) -> float:
    """扫每步 raw 里的 <tool_call>，提取 JSON 并校验；坏 JSON 计入分母不计入分子。

    参数:
        records: 轨迹记录列表

    返回:
        float: JSON 格式合法的工具调用占比
    """
    total, ok = 0, 0
    for r in records:
        for s in r["steps"]:
            # 先尝试匹配完整标签，再尝试匹配截断标签
            m = TOOL_CALL_FULL_RE.search(s.get("raw", ""))
            if not m:
                m = TOOL_CALL_TRUNC_RE.search(s.get("raw", ""))
            if not m:
                continue
            total += 1
            try:
                json.loads(m.group(1))  # 尝试解析 JSON
                ok += 1
            except json.JSONDecodeError:
                pass  # JSON 解析失败，仅计入分母
    return ok / max(total, 1)

if __name__ == "__main__":
    # 演示：用样本记录计算各项指标
    from eval.tasks import SAMPLE_TASKS
    recs = SAMPLE_RECORDS
    print("成功率        :", success_rate(SAMPLE_TASKS, recs))
    print("平均步数      :", sum(step_count(r) for r in recs) / len(recs))
    print("平均 token    :", sum(token_count(r) for r in recs) / len(recs))
    print("JSON 合法率   :", json_valid_rate(recs))