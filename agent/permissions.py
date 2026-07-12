from pathlib import Path

READONLY = {"read", "grep", "glob"}
WRITE    = {"write", "edit"}
EXEC     = {"bash", "web_fetch"}

def check(tool: str, args: dict, workdir: Path) -> str:
    """返回 'allow' / 'confirm' / 'deny'。"""
    if tool == "read":
        path = Path(args.get("path", "")).expanduser().resolve()
        try:
            path.relative_to(workdir.resolve())
        except ValueError:
            return "deny"
        return "allow"
    if tool in READONLY:
        return "allow"
    if tool in WRITE:
        p = Path(args.get("path", "")).resolve()
        # 限制在工作目录内，越界直接拒绝
        return "confirm" if str(p).startswith(str(workdir.resolve())) else "deny"
    if tool in EXEC:
        return "confirm"          # 执行/外传一律先确认（沙箱在步骤 2）
    return "confirm"              # 未知工具：保守，先问