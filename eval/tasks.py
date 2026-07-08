from __future__ import annotations
from dataclasses import dataclass
from typing import Callable
import re

# 一条“轨迹记录”长这样（步骤 2 会给出完整样本）：
#   {"task": "任务名", "steps": [ {tool_calls, raw, prompt_tokens, completion_tokens}, ... ],
#    "final": "agent 的最终自然语言答复"}
Trajectory = dict

@dataclass
class Task:
    name: str
    instruction: str                       # 给 agent 的指令
    check: Callable[[Trajectory], bool]    # 成功判据：吃一条轨迹，判成败

# ---- 成功判据（程序化优先）----
def _check_read_config(traj: Trajectory) -> bool:
    # 成功 = 期间调用过 read 且最终答复里报出了 timeout 的值
    used_read = any(
        tc["name"] == "read"
        for s in traj["steps"] for tc in s.get("tool_calls", [])
    )
    return used_read and "30" in traj.get("final", "")

def _check_list_dir(traj: Trajectory) -> bool:
    return any(
        tc["name"] == "bash" and "ls" in str(tc.get("arguments", {}))
        for s in traj["steps"] for tc in s.get("tool_calls", [])
    )

# TODO[Day3] 再补一条“你组领域”的任务判据（下面 _check_domain）
def _check_domain(traj: Trajectory) -> bool:
    final = traj.get("final", "")
    
    module_patterns = {
        "活动方案": r"活动(?:方案|策划|内容|安排)",
        "预算表":   r"(?:预算|费用|开支|花销)",
        "时间安排": r"(?:时间|日程|排期|timeline|流程)",
        "人员分工": r"(?:分工|负责人|职责|统筹)",
        "宣传文案": r"(?:宣传|文案|推文|海报|宣发)",
        "风险预案": r"(?:风险|预案|应急|备选|突发)",
    }
    
    hit_count = sum(1 for p in module_patterns.values() if re.search(p, final))
    modules_ok = hit_count >= 3

    budget_ok = False
    budget_match = re.search(r"(?:总计|总预算|合计|总共|预算)[^\d]{0,15}(\d+(?:\.\d{1,2})?)", final)
    if budget_match:
        try:
            budget_ok = float(budget_match.group(1)) <= 1000
        except ValueError:
            pass
            
    return modules_ok and budget_ok

SAMPLE_TASKS: list[Task] = [
    Task("read-config", "读取 config.json，告诉我 timeout 是多少", _check_read_config),
    Task("list-dir", "列出当前目录下的文件", _check_list_dir),
    Task("activity-design", "帮我们设计一个书画社招新宣传活动方案，预算控制在300元以内", _check_domain),
    # 可再加 1 条
]