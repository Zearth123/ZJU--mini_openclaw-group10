"""受控 shell 执行（Day4：bash；Day8：加沙箱与权限）。"""
from __future__ import annotations
from .base import Tool
import shutil, subprocess
from pathlib import Path

DENY = ("rm -rf /", ":(){", "mkfs", "dd if=", "> /dev/sd", "curl", "wget")  # 兜底黑名单


def _bash(command: str, timeout: int = 30) -> str:
    normalized = command.lower().strip()
    if any(bad in normalized for bad in DENY):
        return f"[沙箱] 拒绝执行高危命令：{command}"

    workdir = Path.cwd().resolve()

    if shutil.which("bwrap"):
        cmd = [
            "bwrap",
            "--die-with-parent",
            "--new-session",
            "--unshare-net",
            "--ro-bind", "/", "/",
            "--bind", str(workdir), str(workdir),
            "--chdir", str(workdir),
            "--dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",
            "bash", "-c", command,
        ]
    else:
        # 这不是沙箱，只是无 bwrap 时的降级路径。
        cmd = ["bash", "-c", command]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=workdir,
        )
    except subprocess.TimeoutExpired:
        return f"[超时] 命令超过 {timeout}s 未结束：{command}"
    except OSError as exc:
        return f"[执行失败] {exc}"

    output = result.stdout or ""

    if result.stderr:
        output += f"\n[stderr]\n{result.stderr}"

    if result.returncode != 0:
        output += f"\n[returncode={result.returncode}]"

    return output.strip() or "[无输出]"

bash_tool = Tool(
    name="bash",
    description="在工作目录中执行一条 shell 命令并返回输出。",
    parameters={"type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]},
    run=_bash,
)
