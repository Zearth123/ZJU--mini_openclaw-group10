"""受控 shell 执行（Day 6：黑名单兜底 + bubblewrap 沙箱）。"""
from __future__ import annotations  # 延迟求值类型注解

import shlex  # shell 命令字符串分词
import shutil  # 查找系统可执行文件（如 bwrap）
import subprocess  # 运行子进程
from pathlib import Path  # 跨平台路径操作

from .base import Tool  # 工具基类


DENY = (  # 黑名单：包含这些模式的高危命令将被直接拒绝执行
    "rm -rf /",  # 删除根目录
    "rm -rf ~",  # 删除家目录
    ":(){",      # fork 炸弹
    "mkfs",      # 格式化磁盘
    "dd if=",    # 危险磁盘写入
    "> /dev/sd", # 直接写块设备
    "curl",      # 禁用任意 HTTP 请求（使用 web_fetch 替代）
    "wget",      # 禁用任意 HTTP 下载（使用 web_fetch 替代）
)

def _fallback_paths_are_safe(command: str, workdir: Path) -> bool:
    """降级模式下的路径安全检查：确保所有路径参数都在工作目录内。

    注意：这不是完整的 shell 解析器，仅做保守的兜底检查。
    """
    try:
        tokens = shlex.split(command)  # 先做 shell 分词
    except ValueError:
        return False  # 无法分词的命令直接拒绝

    for token in tokens:
        # 去掉常见重定向前缀，覆盖 >/etc/x、2>>/etc/x 等形式。
        candidate = token.lstrip("0123456789<>")
        if not candidate:
            continue

        path = Path(candidate)
        if path.is_absolute():
            # 绝对路径必须解析到工作目录内
            if not path.resolve().is_relative_to(workdir):
                return False
        elif ".." in path.parts:
            # 相对路径不允许使用 .. 跳出工作目录
            return False

    return True


def _bash(
    command: str,
    timeout: int = 30,
    workdir: str | Path | None = None,
) -> str:
    """在隔离沙箱环境中执行 shell 命令；优先使用 bubblewrap 进行系统级隔离。

    没有 bwrap 时降级为黑名单 + 路径白名单检查。workdir 由 AgentLoop 传入以保证安全。
    """
    if not isinstance(command, str) or not command.strip():
        return "[沙箱] 拒绝执行空命令"

    # 对命令做规范化小写匹配，检查是否命中黑名单
    normalized = " ".join(command.casefold().split())
    if any(bad in normalized for bad in DENY):
        return f"[沙箱] 拒绝执行高危命令：{command}"

    # workdir 由 AgentLoop 提供，属于主循环掌握的可信安全边界。
    # 工具 schema 不向模型暴露该参数，且 AgentLoop 会删除模型伪造的 workdir。
    trusted_workdir = Path(workdir or Path.cwd()).resolve()
    bwrap = shutil.which("bwrap")  # 查找系统是否安装 bubblewrap

    if bwrap:
        # 使用 bubblewrap 沙箱：系统目录只读；仅当前工作目录重新挂载为可写；网络命名空间隔离。
        cmd = [
            bwrap,
            "--die-with-parent",           # 父进程退出时子进程自动终止
            "--ro-bind", "/", "/",          # 整个根文件系统只读挂载
            "--bind", str(trusted_workdir), str(trusted_workdir),  # 工作目录可写
            "--chdir", str(trusted_workdir),  # 设置工作目录
            "--unshare-net",                 # 隔离网络命名空间
            "--dev", "/dev",                 # 挂载 /dev
            "--proc", "/proc",               # 挂载 /proc
            "bash", "-c", command,
        ]
    else:
        # 降级模式不能提供真正的文件系统/网络隔离，路径检查只是兜底。
        if not _fallback_paths_are_safe(command, trusted_workdir):
            return f"[沙箱-降级] 拒绝访问工作目录外路径：{command}"
        cmd = ["bash", "-c", command]

    def run(cmd_to_run: list[str]) -> subprocess.CompletedProcess[str]:
        """统一的子进程执行函数，带超时控制。"""
        return subprocess.run(
            cmd_to_run,
            cwd=trusted_workdir,
            capture_output=True,  # 同时捕获 stdout 和 stderr
            text=True,            # 以文本模式返回输出
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
            # bwrap 可用但 namespace 创建失败，降级到黑名单模式
            if not _fallback_paths_are_safe(command, trusted_workdir):
                return f"[沙箱-降级] 拒绝访问工作目录外路径：{command}"
            sandbox_note = "[沙箱-降级] bwrap 不可用，已使用黑名单与路径校验兜底\n"
            p = run(["bash", "-c", command])  # 降级重试
    except subprocess.TimeoutExpired:
        return f"[超时] 命令超过 {timeout}s 未结束：{command}"

    out = p.stdout or ""
    if p.stderr:
        out += f"\n[stderr]\n{p.stderr}"
    if p.returncode != 0:
        out += f"\n[returncode={p.returncode}]"
    return (sandbox_note + out).strip() or "[无输出]"

# 注册为名为 "bash" 的工具，供模型调用执行 shell 命令
bash_tool = Tool(
    name="bash",
    description="在工作目录中执行一条 shell 命令并返回输出。",
    parameters={"type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]},
    run=_bash,
)