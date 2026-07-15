"""ReAct 主循环（Agent 的心脏）。

  while 没到最终答复:
      assistant = backend.chat(messages, tools)      # 模型这一步：思考 or 调工具
      if assistant 有 tool_calls:
          for call in tool_calls:
              obs = registry.get(call.name).run(**call.arguments)   # 执行工具
              messages.append(tool_result(obs))                     # 注入 observation
      else:
          return assistant.content                                 # 最终答复

Day4 你要把下面的 run() 真正实现出来（随工具集扩展逐步完善）。骨架已给出结构与防呆上限。
"""
from __future__ import annotations
import json             # JSON 序列化，用于日志输出
import sys              # 标准错误输出
from typing import Any  # 通用类型注解
from pathlib import Path# 文件路径操作
import argparse
import os
from tools.base import ToolRegistry                     # 工具注册表
from agent.context import maybe_compact, truncate_observation  # 上下文管理
from agent.event_project import EventProject            # 活动项目领域模型
from agent.planning import with_retry                   # 重试机制
from tools.planning import TODO, reset_todo             # 任务清单
from . import permissions                               # 权限检查模块


# 任务清单标题行：在系统消息中插入当前待办
TODO_HEADING = "# 当前任务清单（推进它，别跑偏）\n"
# 当检测到连续无进展时注入的重规划提示
REPLAN_MESSAGE = (
    "检测到任务连续无进展或重复调用同一工具。请检查失败原因，必要时调整清单，"
    "不要重复已失败的相同动作。"
)
# 活动策划领域工具的集合，用于特殊观察处理
DOMAIN_TOOLS = {"calculate_budget", "build_schedule", "validate_project"}

class AgentLoop:
    """ReAct 主循环：管理 model ↔ tool 的迭代交互，直到任务完成或达到上限。"""

    def __init__(self, backend: Any, registry: ToolRegistry, system_prompt: str,
                 max_turns: int = 40,workdir: str | Path | None = None,
                 auto_approve: bool = False, verbose: bool = False,
                 tracer: Any | None = None,
                 confirm_callback: Any | None = None):
        self.backend = backend                              # LLM 后端（DeepSeek / FakeBackend）
        self.registry = registry                            # 工具注册表
        self.system_prompt = system_prompt                  # 系统提示词
        self.max_turns = max_turns                          # 防死循环：硬上限
        self.workdir = Path(workdir or ".").resolve()       # 工作目录
        self.auto_approve = auto_approve                    # 是否自动批准工具调用
        self.verbose = verbose                              # 是否打印详细日志
        self.tracer = tracer                                # 轨迹记录器
        self.confirm_callback = confirm_callback            # 用户确认回调
        self.event_project = EventProject().model_dump(mode="json")  # 活动项目状态
    def run(self, user_task: str, image_paths: list[str] | None = None,
            document_paths: list[str] | None = None) -> str:
        """执行用户任务：持续调用后端模型并执行工具，直到模型返回最终答复。

        Args:
            user_task: 用户输入的自然语言任务。
            image_paths: 随任务提供的图片路径列表（多模态）。
            document_paths: 随任务提供的 PDF/DOCX 文档路径列表（内容会提取为文本注入 prompt）。
        """
        from backend.images import user_content
        from backend.documents import extract_document_text

        # 若提供了文档路径，提取文本并拼接到 user_task 前面
        if document_paths:
            doc_texts: list[str] = []
            for doc_path in document_paths:
                try:
                    text = extract_document_text(doc_path)
                    # 截断单个文档以防撑爆上下文（~50K chars 约 12K tokens）
                    if len(text) > 50_000:
                        text = text[:50_000] + "\n... [文档过长，已截断]"
                    doc_texts.append(f"--- 文件 {doc_path} 的内容 ---\n{text}")
                except Exception as exc:
                    doc_texts.append(f"--- 文件 {doc_path} 读取失败：{exc} ---")
            header = "以下是为任务提供的文档内容（请参考其中的信息完成任务）：\n\n"
            user_task = header + "\n\n".join(doc_texts) + "\n\n" + ("=" * 50) + "\n\n" + user_task

        reset_todo()  # 每次新任务重置待办清单
        # 初始化消息列表：系统提示词 + 用户任务
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content(user_task, image_paths)},
        ]
        todo_message: dict[str, Any] | None = None   # 待办清单消息引用
        last_action: tuple[str, str] | None = None    # 上一次工具调用记录
        repeated_actions = 0                          # 连续重复同一个工具的计数
        no_progress_steps = 0                         # 连续无进展步数
        failure_counts: dict[int, int] = {}           # 每个待办任务的失败次数
        validation_attempts = 0                       # 统一校验尝试次数

        # === ReAct 主循环：每轮调用后端 → 解析 tool_calls → 执行工具 → 注入结果 ===
        for _step in range(1, self.max_turns + 1):
            # 如有待办清单，动态注入到系统消息中
            if TODO.items:
                content = TODO_HEADING + TODO.render()
                if todo_message is None:
                    todo_message = {"role": "system", "content": content}
                    messages.insert(1, todo_message)
                else:
                    todo_message["content"] = content

            # 调用后端模型：传入消息历史和工具定义
            schemas = self.registry.schemas()
            assistant = self.backend.chat(messages, tools=schemas)
            # 将模型回复追加到消息列表
            messages.append({"role": "assistant",
                             "content": assistant.get("content", ""),
                             "tool_calls": assistant.get("tool_calls", [])})

            tool_calls = assistant.get("tool_calls") or []
            # 如有轨迹记录器，记录当前步的调用信息
            if self.tracer is not None:
                usage = assistant.get("usage") or {}
                self.tracer.log_step(
                    _step,
                    tool_calls,
                    int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)),
                    note="tool round" if tool_calls else "final response",
                )
            # 模型未生成工具调用：视为最终答复，直接返回
            if not tool_calls:
                return assistant.get("content", "")

            # === 执行工具调用阶段 ===
            before = TODO.snapshot()  # 执行前的快照，用于检测进展
            for call in tool_calls:
                name = call["name"]
                arguments = dict(call.get("arguments", {}))  # 转为可变字典，后面会修改路径参数
                tool = self.registry.get(name)

                # 将工具参数中的相对文件路径解析为 workdir 内的绝对路径
                if tool is not None:
                    for path_key in ("path",):
                        p = arguments.get(path_key)
                        if isinstance(p, str) and p.strip():
                            path = Path(p)
                            if not path.is_absolute():
                                arguments[path_key] = str((self.workdir / path).resolve())
                    # 为 bash 和 glob 工具注入 workdir（参数不会暴露给模型）
                    if name == "bash":
                        arguments["workdir"] = str(self.workdir)
                    if name == "glob":
                        arguments["workdir"] = str(self.workdir)

                # verbose 模式下打印工具调用信息
                if self.verbose:
                    rendered_args = json.dumps(arguments, ensure_ascii=False)
                    print(f"[tool] {name} {rendered_args}", file=sys.stderr)

                # 检测连续重复调用同一工具
                action = (name, repr(sorted(arguments.items())))
                if action == last_action:
                    repeated_actions += 1
                else:
                    last_action = action
                    repeated_actions = 1

                # 工具不存在时的错误处理
                if tool is None:
                    obs = f"错误：未知工具 {name}"
                else:
                    try:
                        # 步骤 1：权限检查（allow / confirm / deny）
                        verdict = permissions.check(
                            name,
                            arguments,
                            self.workdir,
                        )

                        if verdict == "deny":
                            obs = "[权限层] 拒绝：越界写入 / 危险操作"

                        elif verdict == "confirm" and not self.auto_approve:
                            # 步骤 2：需用户确认的工具
                            approved = bool(
                                self.confirm_callback
                                and self.confirm_callback(name, arguments)
                            )
                            if approved:
                                result = with_retry(
                                    lambda: tool.run(**arguments), max_tries=3
                                )
                                if result is None:
                                    raise RuntimeError("瞬时错误重试 3 次后仍失败")
                                obs = result
                            else:
                                obs = f"[权限层] 用户未批准：{name}({arguments})"

                        else:
                            # 步骤 3：允许执行，自动放行
                            # 统一校验超过 3 次上限时直接返回失败
                            if name == "validate_project" and validation_attempts >= 3:
                                result = json.dumps({
                                    "ok": False,
                                    "error": "已达到三次统一校验上限",
                                }, ensure_ascii=False)
                            else:
                                result = with_retry(
                                    lambda: tool.run(**arguments),
                                    max_tries=3,
                                )
                            if result is None:
                                raise RuntimeError("瞬时错误重试 3 次后仍失败")
                            obs = result
                            # 领域工具的特殊处理：解析 JSON 并更新 EventProject
                            if name in DOMAIN_TOOLS:
                                obs, parsed = self._domain_observation(name, result, arguments)
                                if name == "validate_project" and parsed is not None:
                                    validation_attempts += 1
                                    if parsed.get("valid") is False:
                                        if validation_attempts >= 3:
                                            obs += "\n[协调器] 已达到三次校验上限，请明确报告剩余问题。"
                                        else:
                                            obs += "\n[协调器] 请按 violations 修订对应模块后重新校验。"

                    except Exception as exc:
                        # 工具执行异常处理
                        obs = f"工具 {name} 执行出错：{exc}"
                        active_id = TODO.active_id()
                        if active_id is not None:
                            failure_counts[active_id] = failure_counts.get(active_id, 0) + 1
                            if failure_counts[active_id] >= 3:
                                TODO.update(active_id, "blocked")
                                obs += f"；todo {active_id} 已标记 blocked，请先推进其它任务"

                # 连续重复调用的重规划提示
                if repeated_actions >= 3:
                    obs = REPLAN_MESSAGE + "\n" + str(obs)

                # 将工具执行结果作为 tool 角色消息追加到列表
                messages.append({
                    "role": "tool",
                    "name": name,
                    "tool_call_id": call.get("id"),
                    "content": truncate_observation(str(obs)),
                })

                # verbose 模式下打印工具结果
                if self.verbose:
                    print(f"[result] {truncate_observation(str(obs), 500)}", file=sys.stderr)
                    if name in {"todo_write", "update_todo"} and TODO.items:
                        print("[todo]\n" + TODO.render(), file=sys.stderr)

            # === 检测进展：本轮是否有任务状态变化 ===
            after = TODO.snapshot()
            if after == before:
                no_progress_steps += 1
            else:
                no_progress_steps = 0

            # 连续无进展或重复工具调用：注入重规划提示
            if no_progress_steps >= 4 or repeated_actions >= 3:
                messages.append({"role": "system", "content": REPLAN_MESSAGE})

            # 检测本轮新完成的任务，注入反思检查提示
            completed_now = {
                item_id for item_id, status in after if status == "completed"
            } - {
                item_id for item_id, status in before if status == "completed"
            }
            if completed_now:
                messages.append({
                    "role": "system",
                    "content": (
                        "反思检查：刚完成的子任务是否有证据验证、是否引入回归？"
                        "若有问题先修正，再推进下一项。"
                    ),
                })

            # 上下文压缩：超预算时对较早历史做摘要
            messages = maybe_compact(messages, self.backend)

        return self._limit_report("已达步数上限")

    @staticmethod
    def _limit_report(reason: str) -> str:
        """达到最大步数上限时的报告：返回截止原因和当前任务进度。"""
        progress = TODO.render() or "（尚未建立任务清单）"
        return f"{reason}，当前进度：\n{progress}"

    def _domain_observation(
        self, name: str, result: Any, arguments: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        """处理领域工具（预算/排期/校验）的返回结果：解析 JSON 并更新 EventProject 状态。"""
        try:
            parsed = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return f"[工具协议错误] {name} 未返回合法 JSON：{result}", None
        if not isinstance(parsed, dict):
            return f"[工具协议错误] {name} 返回值必须是 JSON 对象", None
        # 工具返回 ok=false：参数错误，提示模型修改后重试
        if parsed.get("ok") is False:
            return f"[参数错误] {parsed.get('error', '未知错误')}，请修改参数后重试。", parsed
        # 预算工具：更新预算限制和预算计算结果到 EventProject
        if name == "calculate_budget":
            self.event_project["brief"]["budget_limit"] = arguments.get(
                "budget_limit", self.event_project["brief"]["budget_limit"]
            )
            self.event_project["budget"] = parsed
        # 排期工具：更新活动起止时间和排期结果到 EventProject
        elif name == "build_schedule":
            self.event_project["brief"].update({
                "event_start": arguments.get("event_start"),
                "event_end": arguments.get("event_end"),
            })
            self.event_project["schedule"] = parsed
        # 校验工具：更新项目数据和校验结果到 EventProject
        else:
            project = arguments.get("project")
            if isinstance(project, dict):
                self.event_project = project
            self.event_project["validation"] = parsed
        return json.dumps(parsed, ensure_ascii=False, indent=2), parsed
