from pathlib import Path
import shlex
from agent.output import current_output_dir, resolve_artifact_path

READONLY = {"read", "grep", "glob"}
WRITE    = {"write", "edit"}
EXEC     = {"bash", "web_fetch"}
MEMORY_WRITE = {"remember"}
PLANNING = {"todo_write", "update_todo"}
DOMAIN_SAFE = {"calculate_budget", "build_schedule", "validate_project"}
DANGEROUS_COMMANDS = ("rm -rf", "mkfs", "dd if=", "format ", "del /s", "rmdir /s")


def _inside(path_value: object, root: Path) -> bool:
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve().is_relative_to(root)


SAFE_COMMANDS = {
    "pwd", "ls", "rg", "grep", "cat", "head", "tail", "wc", "stat",
    "file", "sort", "uniq", "diff", "jq", "tree", "du", "sed", "find",
}
SAFE_GIT_SUBCOMMANDS = {
    "status", "diff", "log", "show", "branch", "rev-parse", "ls-files",
    "grep", "shortlog", "describe",
}
SHELL_OPERATORS = {"|", "&&", "||"}


def _safe_gzh_script(segment: list[str], root: Path) -> bool:
    program = Path(segment[0]).name
    args = segment[1:]
    if program in {"python", "python3"}:
        if not args:
            return False
        script, script_args = args[0], args[1:]
    else:
        script, script_args = segment[0], args
    script_path = Path(script)
    if not script_path.is_absolute():
        script_path = root / script_path
    try:
        relative = script_path.resolve().relative_to(root)
    except ValueError:
        return False
    allowed = {
        Path("skills/gzh-design/scripts/validate_gzh_html.py"),
        Path("skills/gzh-design/scripts/wrap_preview.py"),
    }
    if relative not in allowed or len(script_args) != 1:
        return False
    target = Path(script_args[0])
    if not target.is_absolute():
        target = root / target
    output_dir = current_output_dir()
    return (
        output_dir is not None
        and target.resolve().is_relative_to(output_dir.resolve())
        and target.suffix.casefold() == ".html"
    )


def _safe_shell_command(command: object, root: Path) -> bool:
    if not isinstance(command, str) or not command.strip():
        return False
    command = command.replace(" 2>/dev/null", "").replace(" 2>&1", "")
    if chr(96) in command or any(token in command for token in ("$(", ">", "<", ";", "\n", "\r")):
        return False
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return False
    if not tokens:
        return False

    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in SHELL_OPERATORS:
            if not segments[-1]:
                return False
            segments.append([])
        elif token == "&":
            return False
        else:
            segments[-1].append(token)
    if not segments[-1]:
        return False

    for segment in segments:
        program = Path(segment[0]).name
        args = segment[1:]
        if program == "git":
            subcommand = next((arg for arg in args if not arg.startswith("-")), "")
            if subcommand not in SAFE_GIT_SUBCOMMANDS:
                return False
        elif program == "find":
            if any(arg in {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fls", "-fprint", "-fprint0"} for arg in args):
                return False
        elif program == "sed":
            if any(arg == "-i" or arg.startswith("-i") for arg in args):
                return False
        elif program in {"python", "python3"} or program.endswith(".py"):
            if not _safe_gzh_script(segment, root):
                return False
        elif program not in SAFE_COMMANDS:
            return False
    return True

def check(tool: str, args: dict, workdir: Path) -> str:
    """返回 'allow' / 'confirm' / 'deny'。"""
    root = workdir.resolve()
    if tool in PLANNING or tool in DOMAIN_SAFE:
        return "allow"
    if tool in {"read", "grep"}:
        return "allow" if _inside(args.get("path", "."), root) else "deny"
    if tool == "glob":
        pattern = args.get("pattern", "")
        if not isinstance(pattern, str) or not pattern.strip():
            return "deny"
        parts = Path(pattern).parts
        return "deny" if Path(pattern).is_absolute() or ".." in parts else "allow"
    if tool in WRITE:
        if not _inside(args.get("path"), root):
            return "deny"
        output_dir = current_output_dir()
        routed = resolve_artifact_path(args.get("path"))
        if output_dir is not None and routed.resolve().is_relative_to(output_dir):
            return "allow"
        return "confirm"
    if tool in EXEC:
        if tool == "bash":
            command = str(args.get("command", ""))
            normalized = command.casefold()
            if any(fragment in normalized for fragment in DANGEROUS_COMMANDS):
                return "deny"
            if _safe_shell_command(command, root):
                return "allow"
        return "confirm"          # 执行/外传一律先确认（沙箱在步骤 2）
    if tool in MEMORY_WRITE:
        return "confirm"
    if tool.startswith("mcp__"):
        operation = tool[5:].casefold()
        if any(word in operation for word in ("read", "list", "search")):
            return "allow"
        return "confirm"
    return "confirm"              # 未知工具：保守，先问
