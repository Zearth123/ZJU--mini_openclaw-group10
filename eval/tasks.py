from __future__ import annotations
from dataclasses import dataclass  # 数据类装饰器，用于定义 Task 结构体
from typing import Callable  # 类型标注：可调用对象（成功判据函数）
import re  # 正则表达式，用于文本匹配检查

# 一条"轨迹记录"长这样（步骤 2 会给出完整样本）：
#   {"task": "任务名", "steps": [ {tool_calls, raw, prompt_tokens, completion_tokens}, ... ],
#    "final": "agent 的最终自然语言答复"}
Trajectory = dict  # 类型别名：轨迹数据字典

@dataclass
class Task:
    """定义一个评测任务：包含任务名称、指令说明和成功判据函数。

    属性:
        name: 任务名称（与轨迹记录中的 task 字段对应）
        instruction: 给 agent 的指令
        check: 成功判据函数，接收一条轨迹，返回 True 表示成功
    """
    name: str
    instruction: str                       # 给 agent 的指令
    check: Callable[[Trajectory], bool]    # 成功判据：吃一条轨迹，判成败

# ---- 成功判据（程序化优先）----
def _check_read_config(traj: Trajectory) -> bool:
    """检查读取配置任务：成功 = 调用过 read 工具且最终答复含 timeout 值。"""
    used_read = any(
        tc["name"] == "read"
        for s in traj["steps"] for tc in s.get("tool_calls", [])
    )
    return used_read and "30" in traj.get("final", "")

def _check_list_dir(traj: Trajectory) -> bool:
    """检查列出目录任务：成功 = 调用过 bash 工具且参数含 ls。"""
    return any(
        tc["name"] == "bash" and "ls" in str(tc.get("arguments", {}))
        for s in traj["steps"] for tc in s.get("tool_calls", [])
    )

# TODO[Day3] 再补一条"你组领域"的任务判据（下面 _check_domain）
def _check_domain(traj: Trajectory) -> bool:
    """检查活动方案设计任务：成功 = 至少覆盖3个模块且预算未超限。

    检查标准：
        - 活动方案、预算表、时间安排、人员分工、宣传文案、风险预案中至少命中3个
        - 最终回答中的预算金额不超过1000元
    """
    final = traj.get("final", "")

    # 定义六个核心模块的正则匹配模式
    module_patterns = {
        "活动方案": r"活动(?:方案|策划|内容|安排)",
        "预算表":   r"(?:预算|费用|开支|花销)",
        "时间安排": r"(?:时间|日程|排期|timeline|流程)",
        "人员分工": r"(?:分工|负责人|职责|统筹)",
        "宣传文案": r"(?:宣传|文案|推文|海报|宣发)",
        "风险预案": r"(?:风险|预案|应急|备选|突发)",
    }

    # 统计命中的模块数量（至少需要3个）
    hit_count = sum(1 for p in module_patterns.values() if re.search(p, final))
    modules_ok = hit_count >= 3

    # 检查预算金额是否在限制以内
    budget_ok = False
    budget_match = re.search(r"(?:总计|总预算|合计|总共|预算)[^\d]{0,15}(\d+(?:\.\d{1,2})?)", final)
    if budget_match:
        try:
            budget_ok = float(budget_match.group(1)) <= 1000
        except ValueError:
            pass

    return modules_ok and budget_ok

# 示例评测任务列表：每个任务包含名称、指令和对应的成功判据
SAMPLE_TASKS: list[Task] = [
    Task("read-config", "读取 config.json，告诉我 timeout 是多少", _check_read_config),
    Task("list-dir", "列出当前目录下的文件", _check_list_dir),
    Task("activity-design", "帮我们设计一个书画社招新宣传活动方案，预算控制在300元以内", _check_domain),
    # TODO: 可根据需要增加更多评测任务
]
