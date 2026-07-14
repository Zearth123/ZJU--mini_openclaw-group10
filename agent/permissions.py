from pathlib import Path       # 路径解析和安全检查

# 工具权限分类：只读操作
READONLY = {"read", "grep", "glob"}
# 工具权限分类：写入操作（需用户确认）
WRITE    = {"write", "edit"}
# 工具权限分类：执行操作（可能产生副作用）
EXEC     = {"bash", "web_fetch"}
# 工具权限分类：记忆写入
MEMORY_WRITE = {"remember"}
# 工具权限分类：任务规划工具
PLANNING = {"todo_write", "update_todo"}
# 工具权限分类：活动策划领域安全工具
DOMAIN_SAFE = {"calculate_budget", "build_schedule", "validate_project"}
# 危险 shell 命令片段黑名单，含此类片段直接拒绝
DANGEROUS_COMMANDS = ("rm -rf", "mkfs", "dd if=", "format ", "del /s", "rmdir /s")


# 检查路径是否在允许的工作目录范围内
def _inside(path_value: object, root: Path) -> bool:
    if not isinstance(path_value, str) or not path_value.strip():
        return False
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = root / path
    return path.resolve().is_relative_to(root)

def check(tool: str, args: dict, workdir: Path) -> str:
    """权限检查主函数：返回 'allow'（允许）/ 'confirm'（需用户确认）/ 'deny'（拒绝）。"""
    root = workdir.resolve()
    # 任务规划和领域工具：直接放行
    if tool in PLANNING or tool in DOMAIN_SAFE:
        return "allow"
    # 只读文件工具：在目录内允许，越界拒绝
    if tool in {"read", "grep"}:
        return "allow" if _inside(args.get("path", "."), root) else "deny"
    # glob 工具：拒绝绝对路径和含 .. 的路径
    if tool == "glob":
        pattern = args.get("pattern", "")
        if not isinstance(pattern, str) or not pattern.strip():
            return "deny"
        parts = Path(pattern).parts
        return "deny" if Path(pattern).is_absolute() or ".." in parts else "allow"
    # 写入工具：在目录内需确认，越界拒绝
    if tool in WRITE:
        return "confirm" if _inside(args.get("path"), root) else "deny"
    # 执行工具：bash 检查危险命令，其余需确认
    if tool in EXEC:
        if tool == "bash":
            command = str(args.get("command", "")).casefold()
            if any(fragment in command for fragment in DANGEROUS_COMMANDS):
                return "deny"
        return "confirm"          # 执行/外传一律先确认（沙箱在步骤 2）
    # 记忆写入：需确认
    if tool in MEMORY_WRITE:
        return "confirm"
    # MCP 工具：读取类放行，写入类需确认
    if tool.startswith("mcp__"):
        operation = tool[5:].casefold()
        if any(word in operation for word in ("read", "list", "search")):
            return "allow"
        return "confirm"
    return "confirm"              # 未知工具：保守，先问
