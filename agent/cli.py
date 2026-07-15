"""命令行入口。

用法：
  python -m agent.cli --selfcheck          # Day1：自检骨架是否装好
  python -m agent.cli "创建 hello.py 并运行"  # Day5 起：真正跑任务（v1 在 Day6）
"""
from __future__ import annotations
import argparse
from datetime import datetime
import uuid     # 命令行参数解析
import os           # 微信公众号 MCP 凭据
import sys          # 系统退出、标准输入判断
from pathlib import Path  # 动态定位项目根目录

from tools.base import build_default_registry   # 创建默认工具注册表（13 个内置工具）
from agent.memory import Memory                  # 持久化记忆
from agent.prompts import SYSTEM_PROMPT          # 系统提示词


# 自检函数：验证所有模块导入和基本功能是否正常
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


# 主入口函数：解析命令行参数，装配运行环境，启动 Agent 循环
def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="mini-openclaw")
    p.add_argument("task", nargs="?", help="要让 agent 完成的任务（自然语言）")
    p.add_argument("--image", action="append", default=[], metavar="PATH",
                   help="随任务发送的图片路径；可重复指定")
    p.add_argument(
        "--document",
        action="append",
        default=[],
        metavar="PATH",
        help="随任务提供的 PDF 或 DOCX 文档路径；可重复指定",
    )
    p.add_argument("--selfcheck", action="store_true", help="只做骨架自检")
    p.add_argument("--trace", metavar="PATH", help="将运行轨迹写入 JSONL 文件")
    p.add_argument("--replay-trace", metavar="PATH", help="回放已有 JSONL 轨迹")
    p.add_argument(
        "--auto-approve",
        action="store_true",
        help="自动批准需要确认的工具，仅用于受控实验",
    )
    p.add_argument(
        "--verbose",
        action="store_true",
        help="显示工具调用、工具结果和 Todo 推进过程",
    )
    args = p.parse_args(argv)

    # 回放模式：不再执行 Agent，直接打印已记录的运行轨迹
    if args.replay_trace:
        from eval.tracer import replay
        replay(args.replay_trace)               # 回放：逐步打印已记录的轨迹
        return 0

    if args.selfcheck or not args.task:
        return selfcheck()                      # 自检模式或无任务时执行自检

    # === 任务执行流程：装配环境 → 构建 Agent → 运行 ===
    from agent.loop import AgentLoop
    reg = build_default_registry()                     # 1. 构建工具注册表
    mcp_clients = []                                   # 2. 初始化 MCP 客户端列表
    # 配置 MCP 服务器启动命令：文件系统服务器。
    # 动态定位项目根目录，避免写死某台机器上的绝对路径。
    project_root = Path(__file__).resolve().parents[1]
    commands = [
        [
            "npx",
            "-y",
            "@modelcontextprotocol/server-filesystem",
            str(project_root),
        ],
    ]
    from mcp.client import MCPClient, register_mcp_tools
    # 逐个启动 MCP 服务器并将工具注册到工具注册表
    for command in commands:
        try:
            mcp = MCPClient(command)
            mcp.start()
            register_mcp_tools(reg, mcp)
            mcp_clients.append(mcp)
        except Exception as e:  # noqa
            print(f"[提示] MCP 未接入（{e}），仅用内置工具。")

    # 读取微信凭据：优先环境变量，其次配置文件，都不设则跳过
    wechat_appid = os.environ.get("WECHAT_APPID", "")
    wechat_secret = os.environ.get("WECHAT_APPSECRET", "")
    if not wechat_appid or not wechat_secret:
        creds_path = os.path.expanduser("~/.claude/credentials/wechat.json")
        if os.path.isfile(creds_path):
            try:
                import json as _json
                _creds = _json.loads(open(creds_path).read())
                wechat_appid = _creds.get("WECHAT_APPID", "")
                wechat_secret = _creds.get("WECHAT_APPSECRET", "")
            except Exception:
                pass

    if wechat_appid and wechat_secret:
        try:
            wechat_mcp = MCPClient(
                [sys.executable, "-m", "mcp.wechat_mp_server"],
                env={
                    "WECHAT_APPID": wechat_appid,
                    "WECHAT_APPSECRET": wechat_secret,
                },
            )
            wechat_mcp.start()
            register_mcp_tools(reg, wechat_mcp)
            mcp_clients.append(wechat_mcp)
        except Exception as e:  # noqa
            print(f"[warn] 微信公众号 MCP 未接入（{e}）")

    # 初始化 LLM 后端：优先使用 DeepSeek，失败则回退到 FakeBackend
    try:
        from backend.client import DeepSeekBackend
        backend = DeepSeekBackend()                       # 需要 DEEPSEEK_API_KEY
    except Exception as e:  # noqa
        from backend.fake_backend import FakeBackend
        print(f"[提示] 未启用真后端（{e}），回退 FakeBackend。配置 DEEPSEEK_API_KEY 后即用真模型。")
        backend = FakeBackend()
    # 加载技能模块：从技能目录加载 SKILL.md 文件
    from skills.loader import (
        load_relevant_skills,
        load_skills,
        skill_detail,
        skills_catalog,
    )
    skills = load_skills()
    # 组装系统提示词：基础提示 + 技能目录 + 项目记忆
    system = SYSTEM_PROMPT + "\n\n# 可用 Skills（相关时按其流程执行）\n" + skills_catalog(skills)

    # 只把最相关的 1-2 个 Skill 的简要说明注入上下文，避免撑大提示词。
    # 完整的 skill 正文在 agent 运行时按需由 LLM 自行决定是否参考。
    relevant_skills = load_relevant_skills(args.task, skills)
    if relevant_skills:
        system += "\n\n## 当前最匹配的 Skill\n"
        for skill in relevant_skills[:2]:
            # 只取描述 + 步骤/流程部分，不包含完整模板和参考文档
            body_lines = skill.body.split("\n")
            trimmed_body = []
            capture = True
            for line in body_lines:
                # 遇到 "## 可用的参考模板"、"## 可调用的工具"、"## 输出格式" 等尾部章节就截断
                if line.startswith("## ") and any(kw in line for kw in ["模板", "工具", "Tool", "输出格式", "注意事项", "参考"]):
                    capture = False
                if capture:
                    trimmed_body.append(line)
            system += f"\n**{skill.name}**: {skill.description}\n\n"
            system += "\n".join(trimmed_body[:80]) + "\n"  # 最多 80 行正文

    # 召回项目记忆：从 MEMORY.md 读取历史信息并注入系统提示
    recalled = Memory("MEMORY.md").recall()
    if recalled.strip():
        system += "\n\n# 关于本项目 / 用户的已知记忆（相关时遵循）\n" + recalled

    # 初始化轨迹记录器（用于调试和评估回放）
    tracer = None
    if args.trace:
        from eval.tracer import Tracer
        tracer = Tracer(args.trace)

    # 用户确认回调函数：请求用户批准需确认的工具调用
    def confirm(name: str, arguments: dict) -> bool:
        if not sys.stdin.isatty():
            return False
        answer = input(f"允许执行 {name} {arguments}? [y/N] ").strip().casefold()
        return answer in {"y", "yes"}

    # 装配 Agent 主循环并执行任务
    run_name = datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]
    output_dir = project_root / "output" / run_name
    print(f"[output] {output_dir}")

    agent = AgentLoop(
        backend,
        reg,
        system,
        auto_approve=args.auto_approve,
        verbose=args.verbose,
        tracer=tracer,
        confirm_callback=confirm,
        output_dir=output_dir,
    )
    print(
        agent.run(
            args.task,
            image_paths=args.image,
            document_paths=args.document,
        )
    )
    return 0


# 脚本入口：当直接运行 python agent/cli.py 时调用 main 函数
if __name__ == "__main__":
    sys.exit(main())