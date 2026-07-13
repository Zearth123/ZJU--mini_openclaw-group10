"""命令行入口。

用法：
  python -m agent.cli --selfcheck          # Day1：自检骨架是否装好
  python -m agent.cli "创建 hello.py 并运行"  # Day5 起：真正跑任务（v1 在 Day6）
"""
from __future__ import annotations
import argparse
import sys

from tools.base import build_default_registry
from agent.memory import Memory
from agent.prompts import SYSTEM_PROMPT


def selfcheck() -> int:
    print("== mini-OpenClaw 自检 ==")
    ok = True
    try:
        reg = build_default_registry()
        print(f"[ok] 工具注册表加载成功，当前内置工具数：{len(reg)}（Day5 起会变多）")
        required = {"calculate_budget", "build_schedule", "validate_project"}
        missing = required - set(reg.names())
        if missing:
            raise RuntimeError(f"缺少活动领域工具：{sorted(missing)}")
        print("[ok] 活动预算、排期和统一校验工具已注册")
    except Exception as e:  # noqa
        print(f"[FAIL] 工具注册表：{e}"); ok = False

    try:
        from backend.fake_backend import FakeBackend
        FakeBackend().chat([{"role": "user", "content": "hi"}], tools=[])
        print("[ok] FakeBackend 可用（未配 DEEPSEEK_API_KEY 时的离线占位后端）")
    except Exception as e:  # noqa
        print(f"[FAIL] FakeBackend：{e}"); ok = False

    try:
        from agent.loop import AgentLoop  # noqa
        print("[ok] 主循环模块可导入（Day5 实现 run 逻辑）")
    except Exception as e:  # noqa
        print(f"[FAIL] 主循环：{e}"); ok = False

    print("== 自检", "通过" if ok else "未通过", "==")
    print("\n下一步：按 dayNN 的 lab-guide 填 # TODO 标记。")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mini-openclaw")
    p.add_argument("task", nargs="?", help="要让 agent 完成的任务（自然语言）")
    p.add_argument("--image", action="append", default=[], metavar="PATH",
                   help="随任务发送的图片路径；可重复指定")
    p.add_argument("--selfcheck", action="store_true", help="只做骨架自检")
    p.add_argument("--trace", metavar="PATH", help="将运行轨迹写入 JSONL 文件")
    p.add_argument("--replay-trace", metavar="PATH", help="回放已有 JSONL 轨迹")
    p.add_argument(
    "--auto-approve",
    action="store_true",
    help="自动批准需要确认的工具，仅用于受控实验",)
    p.add_argument(
        "--verbose",
        action="store_true",
        help="显示工具调用、工具结果和 Todo 推进过程",
    )
    args = p.parse_args(argv)

    if args.replay_trace:
        from eval.tracer import replay
        replay(args.replay_trace)
        return 0

    if args.selfcheck or not args.task:
        return selfcheck()

    # 真正跑任务：优先用 DeepSeek API；没配 key 时回退到 FakeBackend（离线打通管道）
    from agent.loop import AgentLoop
    reg = build_default_registry()
    mcp_clients = []
    commands = [
    [
        "npx",
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/minioc/mini-openclaw",
    ],
    ]
    from mcp.client import MCPClient, register_mcp_tools
    for command in commands:
        try:
            mcp = MCPClient(command)
            mcp.start()
            register_mcp_tools(reg, mcp)
            mcp_clients.append(mcp)
        except Exception as e:  # noqa
            print(f"[提示] MCP 未接入（{e}），仅用内置工具。")
    try:
        from backend.client import DeepSeekBackend
        backend = DeepSeekBackend()                       # 需要 DEEPSEEK_API_KEY
    except Exception as e:  # noqa
        from backend.fake_backend import FakeBackend
        print(f"[提示] 未启用真后端（{e}），回退 FakeBackend。配置 DEEPSEEK_API_KEY 后即用真模型。")
        backend = FakeBackend()
    from skills.loader import load_skills, skills_catalog
    skills = load_skills()
    system = SYSTEM_PROMPT + "\n\n# 可用 Skills（相关时按其流程执行）\n" + skills_catalog(skills)

    recalled = Memory("MEMORY.md").recall()
    if recalled.strip():
        system += "\n\n# 关于本项目 / 用户的已知记忆（相关时遵循）\n" + recalled

    tracer = None
    if args.trace:
        from eval.tracer import Tracer
        tracer = Tracer(args.trace)

    def confirm(name: str, arguments: dict) -> bool:
        if not sys.stdin.isatty():
            return False
        answer = input(f"允许执行 {name} {arguments}? [y/N] ").strip().casefold()
        return answer in {"y", "yes"}

    agent = AgentLoop(
        backend,
        reg,
        system,
        auto_approve=args.auto_approve,
        verbose=args.verbose,
        tracer=tracer,
        confirm_callback=confirm,
    )
    print(agent.run(args.task, image_paths=args.image))
    return 0


if __name__ == "__main__":
    sys.exit(main())
