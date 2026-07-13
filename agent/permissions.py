from pathlib import Path

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
        return "confirm" if _inside(args.get("path"), root) else "deny"
    if tool in EXEC:
        if tool == "bash":
            command = str(args.get("command", "")).casefold()
            if any(fragment in command for fragment in DANGEROUS_COMMANDS):
                return "deny"
        return "confirm"          # 执行/外传一律先确认（沙箱在步骤 2）
    if tool in MEMORY_WRITE:
        return "confirm"
    if tool.startswith("mcp__"):
        operation = tool[5:].casefold()
        if any(word in operation for word in ("read", "list", "search")):
            return "allow"
        return "confirm"
    return "confirm"              # 未知工具：保守，先问
