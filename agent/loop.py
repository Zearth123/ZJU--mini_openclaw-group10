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
import json
import sys
from typing import Any
from pathlib import Path

from tools.base import ToolRegistry
from agent.context import maybe_compact, truncate_observation
from agent.event_project import EventProject
from agent.planning import with_retry
from tools.planning import TODO, reset_todo
from . import permissions


TODO_HEADING = "# 当前任务清单（推进它，别跑偏）\n"
REPLAN_MESSAGE = (
    "检测到任务连续无进展或重复调用同一工具。请检查失败原因，必要时调整清单，"
    "不要重复已失败的相同动作。"
)
DOMAIN_TOOLS = {"calculate_budget", "build_schedule", "validate_project"}

class AgentLoop:
    def __init__(self, backend: Any, registry: ToolRegistry, system_prompt: str,
                 max_turns: int = 40,workdir: str | Path | None = None,
                 auto_approve: bool = False, verbose: bool = False,
                 tracer: Any | None = None,
                 confirm_callback: Any | None = None):
        self.backend = backend
        self.registry = registry
        self.system_prompt = system_prompt
        self.max_turns = max_turns          # 防死循环：硬上限
        self.workdir = Path(workdir or ".").resolve()
        self.auto_approve = auto_approve
        self.verbose = verbose
        self.tracer = tracer
        self.confirm_callback = confirm_callback
        self.event_project = EventProject().model_dump(mode="json")
    def run(self, user_task: str, image_paths: list[str] | None = None) -> str:
        from backend.images import user_content

        reset_todo()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_content(user_task, image_paths)},
        ]
        todo_message: dict[str, Any] | None = None
        last_action: tuple[str, str] | None = None
        repeated_actions = 0
        no_progress_steps = 0
        failure_counts: dict[int, int] = {}
        validation_attempts = 0

        for _step in range(1, self.max_turns + 1):
            if TODO.items:
                content = TODO_HEADING + TODO.render()
                if todo_message is None:
                    todo_message = {"role": "system", "content": content}
                    messages.insert(1, todo_message)
                else:
                    todo_message["content"] = content

            schemas = self.registry.schemas()
            assistant = self.backend.chat(messages, tools=schemas)
            messages.append({"role": "assistant",
                             "content": assistant.get("content", ""),
                             "tool_calls": assistant.get("tool_calls", [])})

            tool_calls = assistant.get("tool_calls") or []
            if self.tracer is not None:
                usage = assistant.get("usage") or {}
                self.tracer.log_step(
                    _step,
                    tool_calls,
                    int(usage.get("prompt_tokens", 0)),
                    int(usage.get("completion_tokens", 0)),
                    note="tool round" if tool_calls else "final response",
                )
            if not tool_calls:
                return assistant.get("content", "")

            before = TODO.snapshot()
            for call in tool_calls:
                name = call["name"]
                arguments = call.get("arguments", {})
                tool = self.registry.get(name)

                if self.verbose:
                    rendered_args = json.dumps(arguments, ensure_ascii=False)
                    print(f"[tool] {name} {rendered_args}", file=sys.stderr)

                action = (name, repr(sorted(arguments.items())))
                if action == last_action:
                    repeated_actions += 1
                else:
                    last_action = action
                    repeated_actions = 1

                if tool is None:
                    obs = f"错误：未知工具 {name}"
                else:
                    try:
                        verdict = permissions.check(
                            name,
                            arguments,
                            self.workdir,
                        )

                        if verdict == "deny":
                            obs = "[权限层] 拒绝：越界写入 / 危险操作"

                        elif verdict == "confirm" and not self.auto_approve:
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
                        obs = f"工具 {name} 执行出错：{exc}"
                        active_id = TODO.active_id()
                        if active_id is not None:
                            failure_counts[active_id] = failure_counts.get(active_id, 0) + 1
                            if failure_counts[active_id] >= 3:
                                TODO.update(active_id, "blocked")
                                obs += f"；todo {active_id} 已标记 blocked，请先推进其它任务"

                if repeated_actions >= 3:
                    obs = REPLAN_MESSAGE + "\n" + str(obs)

                messages.append({
                    "role": "tool",
                    "name": name,
                    "tool_call_id": call.get("id"),
                    "content": truncate_observation(str(obs)),
                })

                if self.verbose:
                    print(f"[result] {truncate_observation(str(obs), 500)}", file=sys.stderr)
                    if name in {"todo_write", "update_todo"} and TODO.items:
                        print("[todo]\n" + TODO.render(), file=sys.stderr)

            after = TODO.snapshot()
            if after == before:
                no_progress_steps += 1
            else:
                no_progress_steps = 0

            if no_progress_steps >= 4 or repeated_actions >= 3:
                messages.append({"role": "system", "content": REPLAN_MESSAGE})

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

            messages = maybe_compact(messages, self.backend)

        return self._limit_report("已达步数上限")

    @staticmethod
    def _limit_report(reason: str) -> str:
        progress = TODO.render() or "（尚未建立任务清单）"
        return f"{reason}，当前进度：\n{progress}"

    def _domain_observation(
        self, name: str, result: Any, arguments: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        try:
            parsed = json.loads(result) if isinstance(result, str) else result
        except (json.JSONDecodeError, TypeError):
            return f"[工具协议错误] {name} 未返回合法 JSON：{result}", None
        if not isinstance(parsed, dict):
            return f"[工具协议错误] {name} 返回值必须是 JSON 对象", None
        if parsed.get("ok") is False:
            return f"[参数错误] {parsed.get('error', '未知错误')}，请修改参数后重试。", parsed
        if name == "calculate_budget":
            self.event_project["brief"]["budget_limit"] = arguments.get(
                "budget_limit", self.event_project["brief"]["budget_limit"]
            )
            self.event_project["budget"] = parsed
        elif name == "build_schedule":
            self.event_project["brief"].update({
                "event_start": arguments.get("event_start"),
                "event_end": arguments.get("event_end"),
            })
            self.event_project["schedule"] = parsed
        else:
            project = arguments.get("project")
            if isinstance(project, dict):
                self.event_project = project
            self.event_project["validation"] = parsed
        return json.dumps(parsed, ensure_ascii=False, indent=2), parsed
