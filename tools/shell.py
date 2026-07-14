"""受控 shell 执行（Day 6：黑名单兜底 + bubblewrap 沙箱）。"""
from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from .base import Tool


DENY = (
    "rm -rf /",
    "rm -rf ~",
    ":(){",
    "mkfs",
    "dd if=",
    "> /dev/sd",
    "curl",
    "wget",
)

def _fallback_paths_are_safe(command: str, workdir: Path) -> bool:
    """对无 bwrap 环境做保守的路径检查；它不是完整 shell 解析器。"""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False

    for token in tokens:
        # 去掉常见重定向前缀，覆盖 >/etc/x、2>>/etc/x 等形式。
        candidate = token.lstrip("0123456789<>")
        if not candidate:
            continue

        path = Path(candidate)
        if path.is_absolute():
            if not path.resolve().is_relative_to(workdir):
                return False
        elif ".." in path.parts:
            return False

    return True


def _bash(
    command: str,
    timeout: int = 30,
    workdir: str | Path | None = None,
) -> str:
    """在隔离环境中执行命令；没有 bwrap 时采用保守的降级策略。"""
    if not isinstance(command, str) or not command.strip():
        return "[沙箱] 拒绝执行空命令"

    normalized = " ".join(command.casefold().split())
    if any(bad in normalized for bad in DENY):
        return f"[沙箱] 拒绝执行高危命令：{command}"

    # workdir 由 AgentLoop 提供，属于主循环掌握的可信安全边界。
    # 工具 schema 不向模型暴露该参数，且 AgentLoop 会删除模型伪造的 workdir。
    trusted_workdir = Path(workdir or Path.cwd()).resolve()
    bwrap = shutil.which("bwrap")

    if bwrap:
        # 系统目录只读；仅当前工作目录重新挂载为可写；网络命名空间隔离。
        cmd = [
            bwrap,
            "--die-with-parent",
            "--ro-bind", "/", "/",
            "--bind", str(trusted_workdir), str(trusted_workdir),
            "--chdir", str(trusted_workdir),
            "--unshare-net",
            "--dev", "/dev",
            "--proc", "/proc",
            "bash", "-c", command,
        ]
    else:
        # 降级模式不能提供真正的文件系统/网络隔离，路径检查只是兜底。
        if not _fallback_paths_are_safe(command, trusted_workdir):
            return f"[沙箱-降级] 拒绝访问工作目录外路径：{command}"
        cmd = ["bash", "-c", command]

    def run(cmd_to_run: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd_to_run,
            cwd=trusted_workdir,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

    sandbox_note = ""
    try:
        p = run(cmd)

        # 某些容器/WSL 中能找到 bwrap，但内核禁止创建 namespace。
        # 只对明确的沙箱初始化失败做降级；命令自身失败绝不能重新执行。
        bwrap_unavailable = bwrap and p.returncode != 0 and any(
            marker in (p.stderr or "")
            for marker in (
                "Creating new namespace failed",
                "No permissions to create new namespace",
            )
        )
        if bwrap_unavailable:
            if not _fallback_paths_are_safe(command, trusted_workdir):
                return f"[沙箱-降级] 拒绝访问工作目录外路径：{command}"
            sandbox_note = "[沙箱-降级] bwrap 不可用，已使用黑名单与路径校验兜底\n"
            p = run(["bash", "-c", command])
    except subprocess.TimeoutExpired:
        return f"[超时] 命令超过 {timeout}s 未结束：{command}"
    out = p.stdout or ""
    if p.stderr:
        out += f"\n[stderr]\n{p.stderr}"
    if p.returncode != 0:
        out += f"\n[returncode={p.returncode}]"
    return (sandbox_note + out).strip() or "[无输出]"

bash_tool = Tool(
    name="bash",
    description="在工作目录中执行一条 shell 命令并返回输出。",
    parameters={"type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]},
    run=_bash,
)