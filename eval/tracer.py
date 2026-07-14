"""极小轨迹记录器：一步一行 JSON（JSONL），可回放。"""
from __future__ import annotations
import json, time  # json：序列化事件数据；time：时间戳记录
from pathlib import Path  # 路径操作，跨平台文件路径管理

class Tracer:
    """轨迹记录器：将 agent 的每一步执行记录追加写入 JSONL 文件，可用于事后回放和分析。"""

    def __init__(self, path: str):
        """初始化 tracer，创建（或清空）指定的 JSONL 文件。

        参数:
            path: 输出 JSONL 文件的路径
        """
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)  # 确保父目录存在
        self.path.write_text("", encoding="utf-8")   # 清空/新建

    def log_step(self, step: int, tool_calls: list, prompt_tokens: int,
                 completion_tokens: int, note: str = "") -> None:
        """记录一步执行日志。

        参数:
            step: 步骤编号（从 0 开始）
            tool_calls: 该步调用的工具列表
            prompt_tokens: 该步的 prompt token 数
            completion_tokens: 该步的 completion token 数
            note: 备注信息（如原始输出片段）
        """
        event = {"ts": round(time.time(), 3), "step": step,
                 "tool_calls": tool_calls, "note": note,
                 "prompt_tokens": prompt_tokens,
                 "completion_tokens": completion_tokens}
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")  # 追加写入一行 JSON

def replay(path: str) -> None:
    """把一条 JSONL 轨迹逐步打印出来（回放），同时统计总 token 消耗。"""
    total_tok = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        e = json.loads(line)  # 解析每一行 JSON 事件
        tok = e["prompt_tokens"] + e["completion_tokens"]
        total_tok += tok
        names = [tc["name"] for tc in e["tool_calls"]] or ["(无工具调用)"]
        print(f"  step {e['step']}: 调用 {names}  | 本步 {tok} tok  | {e['note']}")
    print(f"  —— 轨迹共 {total_tok} token")

if __name__ == "__main__":
    # 演示：用 metrics 模块的一条样本记录模拟 agent 逐步执行，写入 JSONL 后回放
    from eval.metrics import SAMPLE_RECORDS
    rec = SAMPLE_RECORDS[0]
    tr = Tracer("eval/trace_sample.jsonl")
    for i, s in enumerate(rec["steps"]):
        tr.log_step(i, s.get("tool_calls", []),
                    s.get("prompt_tokens", 0), s.get("completion_tokens", 0),
                    note=s.get("raw", "")[:40])
    print(f"已写入 eval/trace_sample.jsonl（任务={rec['task']}）；回放：")
    replay("eval/trace_sample.jsonl")
