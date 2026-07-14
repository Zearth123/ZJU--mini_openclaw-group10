"""最小消融：有/无 system-prompt 两组样本轨迹的成功率对比。"""
from eval.tasks import SAMPLE_TASKS  # 从任务模块导入测试任务列表
from eval.metrics import success_rate, token_count  # 从指标模块导入成功率和token计数函数

# A 组：带 system-prompt（agent 被告知”需要时用 <tool_call> 调工具”）——都成功
# 每组记录包含：任务名称、执行步骤列表（含工具调用、原始文本、token计数）、最终答复
GROUP_WITH_SYS = [
    {"task": "read-config",
     "steps": [{"tool_calls": [{"name": "read", "arguments": {"path": "config.json"}}],
                "raw": '<tool_call>{"name":"read","arguments":{"path":"config.json"}}</tool_call>',
                "prompt_tokens": 330, "completion_tokens": 22}],
     "final": "config.json 里 timeout = 30 秒。"},
    {"task": "list-dir",
     "steps": [{"tool_calls": [{"name": "bash", "arguments": {"command": "ls"}}],
                "raw": '<tool_call>{"name":"bash","arguments":{"command":"ls"}}</tool_call>',
                "prompt_tokens": 300, "completion_tokens": 18}],
     "final": "当前目录有：main.py config.json README.md"},
]
# B 组：无 system-prompt（agent 不知道工具约定，直接瞎答）——都失败
# 对比组：没有工具调用规范指引，模型只能凭自身知识回答
GROUP_NO_SYS = [
    {"task": "read-config",
     "steps": [{"tool_calls": [], "raw": "timeout 应该是个常见的默认值。",
                "prompt_tokens": 120, "completion_tokens": 14}],
     "final": "timeout 应该是个常见的默认值。"},
    {"task": "list-dir",
     "steps": [{"tool_calls": [], "raw": "你可以自己用 ls 看看。",
                "prompt_tokens": 110, "completion_tokens": 12}],
     "final": "你可以自己用 ls 看看。"},
]

def summarize(name, recs):
    """汇总一组记录的成功率和平均token消耗。"""
    sr = success_rate(SAMPLE_TASKS, recs)  # 计算该组成功率
    avg_tok = sum(token_count(r) for r in recs) / len(recs)  # 计算平均token数
    print(f"{name:16s} 成功率={sr:.2f}  平均token={avg_tok:.0f}")
    return sr

if __name__ == "__main__":
    # 运行消融实验：对比有/无 system-prompt 两组的效果差异
    print("=== 消融：有/无 system-prompt ===")
    a = summarize("有 system-prompt", GROUP_WITH_SYS)
    b = summarize("无 system-prompt", GROUP_NO_SYS)
    print(f"结论：system-prompt 使成功率 {b:.2f} -> {a:.2f}（Δ={a-b:+.2f}）")