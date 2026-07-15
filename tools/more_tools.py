"""完整工具集：edit / grep / glob（Day4，→ v1）+ web_fetch / task_list（Day5）。

每个工具上午讲设计权衡，下午实现。这里只给签名与 TODO，便于你拆到独立文件。
建议最终拆成 edit.py / search.py / web.py / todo.py，再在 base.build_default_registry 注册。
"""
from __future__ import annotations  # 延迟求值类型注解
from .base import Tool  # 工具基类
import subprocess  # 子进程执行（grep）
from pathlib import Path  # 跨平台路径操作
from urllib.parse import urljoin, urlparse  # URL 解析与拼接

from .external import wrap_external  # 外部内容安全包装


ALLOW_HOSTS = {"example.com", "api.deepseek.com"}  # 白名单：仅允许访问这些域名


def _url_is_allowed(url: str) -> bool:
    """检查 URL 是否在白名单中，防止 SSRF 攻击。"""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.hostname in ALLOW_HOSTS

# --- edit：三种策略权衡（整文件重写 / unified diff / search-replace）
# 最终选择 search-replace，因为模型更容易精确生成原文片段
def _edit(path: str, old: str = "", new: str = "") -> str:
    """在文件中将唯一出现的 old 文本替换为 new。要求 old 在文件中恰好出现一次。"""
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    count = text.count(old)  # 检查 old 出现的次数
    if count == 0:
        return f"[失败] 未找到待替换文本，请照抄文件原文（含缩进）。path={path}"
    if count > 1:
        return f"[失败] old 在文件中出现 {count} 次，不唯一；请扩大 old 片段使其唯一。"
    with open(path, "w", encoding="utf-8") as f:
        f.write(text.replace(old, new, 1))  # 只替换第一次出现
    return f"已在 {path} 完成 1 处替换。"


# --- grep：基于 ripgrep（rg），支持正则搜索和行号显示 ---
def _grep(pattern: str, path: str = ".", max_lines: int = 100) -> str:
    """使用 ripgrep 在文件中搜索文本模式，返回带行号的匹配行。"""
    try:
        # 调用 rg 命令，输出格式为 "文件路径:行号:内容"
        p = subprocess.run(
            ["rg", "--line-number", "--no-heading", pattern, path],
            capture_output=True, text=True, timeout=30,
        )
    except FileNotFoundError:
        return "[失败] 未找到 rg，请先安装 ripgrep。"
    if p.returncode not in (0, 1):  # 1 = 无匹配，属正常
        return f"[grep 出错] {p.stderr.strip()}"
    lines = p.stdout.splitlines()
    if not lines:
        return f"[无匹配] pattern={pattern}"
    if len(lines) > max_lines:
        return "\n".join(lines[:max_lines]) + f"\n... [共 {len(lines)} 行，已截断前 {max_lines} 行]"
    return "\n".join(lines)


# --- glob：按文件名通配模式递归查找文件，不搜索文件内容 ---
def _glob(pattern: str, max_items: int = 100, workdir: str | None = None) -> str:
    """使用 pathlib 的 rglob 按文件名模式查找文件，限制最大返回数量。

    workdir 由 AgentLoop 传入以支持输出目录；工具 schema 不向模型暴露该参数。
    """
    root = Path(workdir).resolve() if workdir else Path(".")
    paths = [str(p) for p in root.rglob(pattern) if p.is_file()]
    if not paths:
        return f"[无匹配] pattern={pattern}"
    if len(paths) > max_items:
        return "\n".join(paths[:max_items]) + f"\n... [共 {len(paths)} 个，已截断前 {max_items} 个]"
    return "\n".join(paths)


# --- web_fetch：URL -> markdown，控制 token 预算，防止 SSRF ---
def _web_fetch(url: str, max_tokens: int = 2000) -> str:
    """抓取 URL 网页内容，转为 markdown 格式并按 token 预算截断。"""
    import httpx  # HTTP 客户端
    from markdownify import markdownify as md  # HTML 转 markdown
    from agent.context import truncate_observation  # 按 token 预算截断文本

    if not _url_is_allowed(url):
        return f"[出站白名单] 拒绝访问未授权地址：{url}"

    # 手动处理重定向：follow_redirects=True 会在检查最终 URL 前就访问恶意域名。
    # 手动检查每次重定向的目标是否仍在白名单内。
    current_url = url
    for _ in range(5):  # 最多跟随 5 次重定向
        resp = httpx.get(current_url, timeout=20, follow_redirects=False)
        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                return "[web_fetch] 重定向响应缺少 Location"
            next_url = urljoin(current_url, location)  # 处理相对 URL
            if not _url_is_allowed(next_url):
                return f"[出站白名单] 拒绝重定向到未授权地址：{next_url}"
            current_url = next_url
            continue
        resp.raise_for_status()
        break
    else:
        return "[web_fetch] 重定向次数超过上限（5）"  # 超过重定向上限

    text = md(resp.text)  # HTML 转 markdown
    text = truncate_observation(text, max_chars=max_tokens * 4)  # 按字符数截断，4 字符约等于 1 token
    return wrap_external(text, f"web:{current_url}")


# --- task_list（已弃用，由 planning.py 中的 todo_write/update_todo 替代）---
def _task_list(action: str, items: list | None = None) -> str:
    """（已弃用）维护结构化待办列表。"""
    # TODO[Day4] 维护一个结构化待办（add/update/complete），作为模型的 scratchpad
    raise NotImplementedError("Day5：实现 task_list")


edit_tool = Tool(
    "edit",
    "编辑已有文本文件：将 path 文件中唯一出现的 old 原文片段替换为 new。"
    "使用前应先 read 文件，old 必须从文件中照抄，包含缩进、空格和换行。"
    "只有 old 恰好出现 1 次时才会修改；若 0 次或多次出现会失败。"
    "适合小范围精确修改，不适合创建新文件；创建新文件请用 write。",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "要编辑的文件路径"},
            "old": {
                "type": "string",
                "description": "待替换的原文片段，必须从文件中精确照抄，并且在文件中唯一出现",
            },
            "new": {
                "type": "string",
                "description": "替换后的新文本",
            },
        },
        "required": ["path", "old", "new"],
    },
    _edit,
)

grep_tool = Tool(
    "grep",
    "按文本内容搜索文件，返回匹配行及其文件路径、行号。"
    "适合查找 TODO、函数名、类名、变量名、报错关键词等。"
    "pattern 是要搜索的文本或正则模式；path 是搜索范围，默认当前目录。"
    "如果需要先找文件名或路径，请用 glob；如果需要查看完整上下文，请再用 read。",
    {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "要搜索的文本或正则模式，例如 TODO、def main、class Agent",
            },
            "path": {
                "type": "string",
                "description": "搜索范围，可以是文件或目录，默认当前目录",
            },
        },
        "required": ["pattern"],
    },
    _grep,
)

glob_tool = Tool(
    "glob",
    "按文件路径通配模式查找文件，只搜索文件名/路径，不搜索文件内容。"
    "适合在不知道具体文件位置时查找文件，例如 '**/*.py'、'agent/*.py'、'*.md'。"
    "找到候选文件后，如需查看内容，请继续使用 read；如需搜索文件内容，请使用 grep。",
    {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "文件路径通配模式，例如 '**/*.py'、'tools/*.py'、'*.md'",
            },
        },
        "required": ["pattern"],
    },
    _glob,
)

web_fetch_tool = Tool(
    "web_fetch",
    "抓取指定 URL 的网页内容，转换为 markdown 后返回，并按 max_tokens 控制长度。"
    "适合读取网页、文档页面、公开说明页等网络资料。"
    "返回内容会自动截断，避免一次抓取撑爆上下文。",
    {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "要抓取的网页 URL，例如 https://example.com",
            },
            "max_tokens": {
                "type": "integer",
                "description": "最大返回 token 预算，默认 2000；实际按 max_tokens*4 字符截断",
            },
        },
        "required": ["url"],
    },
    _web_fetch,
)