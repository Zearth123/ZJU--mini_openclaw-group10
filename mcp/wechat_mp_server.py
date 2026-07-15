"""微信公众号 MCP Server — Python 原生自研实现。

遵循 MCP stdio JSON-RPC 协议（与 echo_server.py 相同的接口模式）。
将微信公众号 API（草稿箱/发布/素材）封装为 MCP 工具。

架构：
  Agent (MCP Client) → stdin/stdout JSON-RPC → WeChatMPServer (本文件) → httpx → 微信公众平台 API

认证方式：
  环境变量 WECHAT_APPID + WECHAT_APPSECRET（在微信公众平台 → 设置与开发 → 基本配置获取）

暴露工具：
  publish_markdown   # 【主力】读取本地 Markdown → 传图 → 创建草稿 → 可选发布，全自动
  upload_image       # 上传本地图片到微信 CDN
  create_draft       # 创建图文草稿（接受 HTML 正文）
  update_draft       # 更新已有草稿
  publish_draft      # 发布草稿（提交至公众号发布队列）
  list_drafts        # 列出草稿列表
  get_draft          # 获取单篇草稿详情

用法（由 agent/cli.py 自动启动）：
  WECHAT_APPID=xxx WECHAT_APPSECRET=yyy python -m mcp.wechat_mp_server
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import mistune

# ── 配置 ──────────────────────────────────────────────────────────────────

WECHAT_API_BASE = "https://api.weixin.qq.com/cgi-bin"


def _get_config() -> dict[str, str]:
    """从环境变量读取微信配置。"""
    appid = os.environ.get("WECHAT_APPID", "")
    secret = os.environ.get("WECHAT_APPSECRET", "")
    if not appid or not secret:
        raise RuntimeError(
            "缺少微信公众平台凭据。请设置环境变量：\n"
            "  export WECHAT_APPID=你的AppID\n"
            "  export WECHAT_APPSECRET=你的AppSecret\n"
            "在 https://mp.weixin.qq.com → 设置与开发 → 基本配置 获取。"
        )
    return {"appid": appid, "secret": secret}


# ── Markdown 工具 ─────────────────────────────────────────────────────────

_markdown_renderer = mistune.create_markdown()


def _md_to_html(md_text: str) -> str:
    """将 Markdown 转为 WeChat 兼容的 HTML。"""
    html = _markdown_renderer(md_text)

    # 后处理：美化引用块（WeChat 默认引用样式太淡）
    html = html.replace(
        "<blockquote>",
        '<blockquote style="border-left: 4px solid #07c160; padding: 8px 16px; margin: 12px 0; background: #f6f6f6; color: #666;">',
    )
    html = html.replace("<blockquote>\n", "<blockquote>")

    # 后处理：代码块加样式
    html = html.replace(
        "<pre>",
        '<pre style="background: #f5f5f5; padding: 12px; border-radius: 4px; overflow-x: auto; font-size: 14px;">',
    )
    html = html.replace(
        "<code>",
        '<code style="background: #f0f0f0; padding: 2px 6px; border-radius: 3px; font-size: 14px;">',
    )
    html = html.replace("</code>\n", "</code>")

    # 后处理：表格加样式
    html = html.replace("<table>", '<table style="border-collapse: collapse; width: 100%; margin: 12px 0;">')
    html = html.replace("<th>", '<th style="border: 1px solid #ddd; padding: 8px; background: #f2f2f2;">')
    html = html.replace("<td>", '<td style="border: 1px solid #ddd; padding: 8px;">')

    # 后处理：图片自适应
    html = html.replace('<img src="', '<img data-src="')
    html = html.replace("/>", ' style="width: 100%; margin: 12px 0;" />')

    return html


def _extract_and_replace_images(md_text: str, uploader: Any, base_dir: Path | None = None) -> str:
    """提取 Markdown 中的本地图片路径，上传到微信 CDN，替换为远程 URL。

    Args:
        md_text: 原始 markdown 文本
        uploader: 具备 upload_image(file_path) -> url 方法的对象

    Returns:
        图片引用已被替换后的 markdown 文本
    """
    pattern = r'!\[([^\]]*)\]\(([^)]+)\)'

    def _replace(match: re.Match) -> str:
        alt = match.group(1)
        path = match.group(2).strip()

        # 已经是 URL 则跳过
        if path.startswith(("http://", "https://", "data:")):
            return match.group(0)

        # 本地文件 → 上传到微信 CDN
        image_path = Path(path).expanduser()
        if not image_path.is_absolute() and base_dir is not None:
            image_path = base_dir / image_path
        abs_path = str(image_path.resolve())
        if not Path(abs_path).is_file():
            print(f"[warn] 图片不存在，跳过: {abs_path}", file=sys.stderr)
            return match.group(0)

        try:
            url = uploader(abs_path)
            print(f"[ok] 图片已上传: {path} → {url[:60]}...", file=sys.stderr)
            return f"![{alt}]({url})"
        except Exception as e:
            print(f"[warn] 图片上传失败 {path}: {e}", file=sys.stderr)
            return match.group(0)

    return re.sub(pattern, _replace, md_text)


def _extract_title(md_text: str) -> str | None:
    """从 Markdown 中提取第一个一级标题作为文章标题。"""
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
        if stripped.startswith("# ") and stripped.startswith("## "):
            # 排除二级标题
            pass
    return None


def _extract_digest(md_text: str, max_len: int = 120) -> str:
    """从 Markdown 中提取前几段纯文本作为摘要。"""
    lines = md_text.splitlines()
    paragraphs = []
    for line in lines:
        stripped = line.strip()
        # 跳过标题、空行、代码块
        if not stripped or stripped.startswith("#") or stripped.startswith("```"):
            continue
        # 去掉 markdown 标记
        text = re.sub(r'[#*`\[\]()>|_-]', '', stripped)
        text = text.strip()
        if text and len(text) > 10:  # 忽略太短的片段
            paragraphs.append(text)
    digest = "".join(paragraphs)
    # 截断到 max_len，尽量在完整词处断
    if len(digest) > max_len:
        digest = digest[:max_len].rsplit("。", 1)[0] + "。"
    return digest or ""


# ── 微信 API 客户端 ──────────────────────────────────────────────────────

class WeChatClient:
    """微信公众号 API 客户端，封装 token 管理与 HTTP 调用。"""

    def __init__(self, appid: str, secret: str):
        self.appid = appid
        self.secret = secret
        self._http = httpx.Client(timeout=30)
        self._token: str = ""
        self._token_expires_at: float = 0

    # ── token 管理 ──────────────────────────────────────────────────────

    def _get_token(self) -> str:
        """获取（或刷新）access_token。"""
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token

        resp = self._http.get(
            f"{WECHAT_API_BASE}/token",
            params={"grant_type": "client_credential", "appid": self.appid, "secret": self.secret},
        )
        data = resp.json()
        if "access_token" not in data:
            raise RuntimeError(f"获取 access_token 失败: {data}")
        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 7200)
        return self._token

    # ── 图片上传 ─────────────────────────────────────────────────────────

    def upload_image(self, file_path: str) -> str:
        """上传本地图片到微信 CDN（media/uploadimg），返回 CDN URL。

        这个 URL 用于文章正文中的图片。不是永久素材 media_id。
        """
        token = self._get_token()
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"图片不存在: {file_path}")

        mime = self._guess_mime(path.suffix)
        files = {
            "media": (path.name, path.read_bytes(), mime),
        }
        resp = self._http.post(
            f"{WECHAT_API_BASE}/media/uploadimg",
            params={"access_token": token},
            files=files,
        )
        data = resp.json()
        if "url" not in data:
            raise RuntimeError(f"上传图片失败: {data}")
        return data["url"]

    def upload_cover_image(self, file_path: str) -> str:
        """上传本地图片为永久素材（material/add_material），返回 media_id。

        这个 media_id 用于草稿的封面图（thumb_media_id）。
        与 upload_image 不同，这个返回的是永久素材 media_id 而非 URL。
        """
        token = self._get_token()
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"封面图片不存在: {file_path}")

        mime = self._guess_mime(path.suffix)
        with open(path, "rb") as f:
            files = {"media": (path.name, f.read(), mime)}
        resp = self._http.post(
            f"{WECHAT_API_BASE}/material/add_material",
            params={"access_token": token, "type": "image"},
            files=files,
        )
        data = resp.json()
        if "media_id" not in data:
            raise RuntimeError(f"上传封面失败: {data}")
        return data["media_id"]

    @staticmethod
    def _guess_mime(suffix: str) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".bmp": "image/bmp",
        }.get(suffix.lower(), "image/png")

    # ── 草稿管理 ─────────────────────────────────────────────────────────

    def create_draft(
        self,
        title: str,
        content: str,
        author: str = "",
        digest: str = "",
        thumb_media_id: str = "",
        need_open_comment: int = 0,
        only_fans_can_comment: int = 0,
        content_source_url: str = "",
    ) -> dict:
        """创建图文草稿。

        Args:
            title: 标题
            content: HTML 正文
            author: 作者（显示在标题下方）
            digest: 摘要（不传则自动截取正文前 120 字）
            thumb_media_id: 封面图片 media_id（建议 900x500 像素）
            need_open_comment: 是否打开评论 0/1
            only_fans_can_comment: 是否仅粉丝可评论 0/1
            content_source_url: 原文链接

        Returns:
            {"media_id": "..."}
        """
        token = self._get_token()
        if not digest:
            digest = re.sub(r"<[^>]+>", "", content)[:120]

        article = {
            "title": title,
            "content": content,
            "digest": digest,
            "need_open_comment": need_open_comment,
            "only_fans_can_comment": only_fans_can_comment,
        }
        if author:
            article["author"] = author
        if thumb_media_id:
            article["thumb_media_id"] = thumb_media_id
        if content_source_url:
            article["content_source_url"] = content_source_url

        resp = self._http.post(
            f"{WECHAT_API_BASE}/draft/add",
            params={"access_token": token},
            json={"articles": [article]},
        )
        data = resp.json()
        if "media_id" not in data:
            raise RuntimeError(f"创建草稿失败: {data}")
        return data

    def update_draft(self, media_id: str, index: int = 0, **fields) -> dict:
        """更新草稿。

        Args:
            media_id: 草稿 media_id
            index: 多图文草稿中的第几篇（从 0 开始）
            **fields: 要修改的字段（title/content/digest/author 等）

        Returns:
            {"errcode": 0, "errmsg": "ok"}
        """
        token = self._get_token()
        # 先获取现有草稿
        existing = self.get_draft(media_id)
        article = existing["article"]
        article.update(fields)

        resp = self._http.post(
            f"{WECHAT_API_BASE}/draft/update",
            params={"access_token": token},
            json={"media_id": media_id, "index": index, "articles": article},
        )
        data = resp.json()
        if data.get("errcode", -1) != 0:
            raise RuntimeError(f"更新草稿失败: {data}")
        return data

    def get_draft(self, media_id: str) -> dict:
        """获取草稿详情。"""
        token = self._get_token()
        resp = self._http.post(
            f"{WECHAT_API_BASE}/draft/get",
            params={"access_token": token},
            json={"media_id": media_id},
        )
        data = resp.json()
        if "news_item" not in data:
            raise RuntimeError(f"获取草稿失败: {data}")
        return {"media_id": media_id, "article": data["news_item"][0]}

    def list_drafts(self, offset: int = 0, count: int = 20, no_content: bool = False) -> dict:
        """列出草稿列表。"""
        token = self._get_token()
        resp = self._http.post(
            f"{WECHAT_API_BASE}/draft/batchget",
            params={"access_token": token},
            json={"offset": offset, "count": min(count, 20), "no_content": 1 if no_content else 0},
        )
        data = resp.json()
        if "item" not in data:
            raise RuntimeError(f"获取草稿列表失败: {data}")
        return data

    # ── 发布管理 ─────────────────────────────────────────────────────────

    def publish_draft(self, media_id: str) -> dict:
        """将草稿提交发布（异步，提交成功后微信会在几分钟内发布）。"""
        token = self._get_token()
        resp = self._http.post(
            f"{WECHAT_API_BASE}/freepublish/submit",
            params={"access_token": token},
            json={"media_id": media_id},
        )
        data = resp.json()
        if data.get("errcode", -1) != 0:
            raise RuntimeError(f"发布草稿失败: {data}")
        return {"publish_id": data.get("publish_id", ""), "msg": "已提交发布，请前往公众号后台查看结果"}

    # ── 默认封面 ─────────────────────────────────────────────────────────

    @staticmethod
    def _generate_default_cover(title: str) -> str:
        """生成一张简单的默认封面图（900x500），返回临时文件路径。

        用 Python 内置模块直接写 PNG，不依赖 Pillow。
        """
        import struct
        import zlib
        import tempfile

        width, height = 900, 500
        bg_color = (7, 193, 96)  # 微信绿

        def _chunk(chunk_type, data):
            c = chunk_type + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        sig = b"\x89PNG\r\n\x1a\n"
        ihdr = _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        raw = b""
        for y in range(height):
            raw += b"\x00" + bytes(bg_color) * width
        idat = _chunk(b"IDAT", zlib.compress(raw))
        iend = _chunk(b"IEND", b"")

        fd, path = tempfile.mkstemp(suffix=".png", prefix="wechat_cover_")
        with os.fdopen(fd, "wb") as f:
            f.write(sig + ihdr + idat + iend)
        return path

    # ── markdown 一站式发布 ──────────────────────────────────────────────

    def create_draft_from_html_file(
        self,
        file_path: str,
        title: str,
        author: str = "",
        digest: str = "",
        publish: bool = False,
        thumb_media_id: str = "",
        need_open_comment: int = 0,
        only_fans_can_comment: int = 0,
        content_source_url: str = "",
    ) -> dict:
        """Create a WeChat draft from a polished gzh-design HTML file."""
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"HTML file not found: {file_path}")
        content = path.read_text(encoding="utf-8").strip()
        if not content or "<section" not in content.lower():
            raise ValueError("HTML must contain a non-empty <section> generated by gzh-design")
        if not thumb_media_id:
            try:
                cover_path = self._generate_default_cover(title)
                thumb_media_id = self.upload_cover_image(cover_path)
                Path(cover_path).unlink(missing_ok=True)
            except Exception as exc:
                print(f"[warn] failed to generate default cover: {exc}", file=sys.stderr)
        draft = self.create_draft(
            title=title, content=content, author=author, digest=digest,
            thumb_media_id=thumb_media_id, need_open_comment=need_open_comment,
            only_fans_can_comment=only_fans_can_comment,
            content_source_url=content_source_url,
        )
        result = {"title": title, "media_id": draft["media_id"], "status": "draft_created"}
        if publish:
            published = self.publish_draft(draft["media_id"])
            result["publish_id"] = published.get("publish_id", "")
            result["status"] = "submitted_for_publish"
        return result

    def publish_markdown(
        self,
        file_path: str,
        title: str = "",
        author: str = "",
        digest: str = "",
        publish: bool = False,
        thumb_media_id: str = "",
        need_open_comment: int = 0,
        only_fans_can_comment: int = 0,
        content_source_url: str = "",
    ) -> dict:
        """一站式：Markdown 文件 → 传图 → 创建草稿 → 可选发布。

        这是智能体的主力工具，单次调用完成全部流程。

        Args:
            file_path: 本地 Markdown 文件路径
            title: 文章标题（不传则从 Markdown 第一个 # 标题提取）
            author: 作者署名
            digest: 摘要（不传则自动截取正文）
            publish: 是否直接发布（默认 false，只存草稿）
            thumb_media_id: 封面 media_id
            need_open_comment: 是否打开评论
            only_fans_can_comment: 仅粉丝可评论
            content_source_url: 原文链接

        Returns:
            包含 media_id 和发布结果的 dict
        """
        # 1. 读取
        path = Path(file_path).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        md_text = path.read_text(encoding="utf-8")

        # 2. 提取标题
        if not title:
            title = _extract_title(md_text) or path.stem

        # 3. 提取摘要
        if not digest:
            digest = _extract_digest(md_text)

        # 4. 上传图片
        md_text = _extract_and_replace_images(md_text, self.upload_image, path.parent)

        # 5. 如果没有封面图，自动生成一张默认封面并上传
        if not thumb_media_id:
            try:
                cover_path = self._generate_default_cover(title)
                thumb_media_id = self.upload_cover_image(cover_path)
                Path(cover_path).unlink(missing_ok=True)
            except Exception as e:
                print(f"[warn] 自动生成封面失败，将无封面创建草稿: {e}", file=sys.stderr)

        # 6. 转 HTML
        html_body = _md_to_html(md_text)
        # 微信正文需要包装在完整 HTML 结构中
        full_html = f"""\
<section style="padding: 16px; line-height: 1.8; font-size: 16px; color: #333;">
{html_body}
</section>"""

        # 7. 创建草稿
        draft = self.create_draft(
            title=title,
            content=full_html,
            author=author,
            digest=digest,
            thumb_media_id=thumb_media_id,
            need_open_comment=need_open_comment,
            only_fans_can_comment=only_fans_can_comment,
            content_source_url=content_source_url,
        )
        result = {
            "title": title,
            "digest": digest,
            "media_id": draft["media_id"],
            "status": "draft_created",
        }

        # 8. 可选发布
        if publish:
            pub = self.publish_draft(draft["media_id"])
            result["publish_id"] = pub.get("publish_id", "")
            result["status"] = "submitted_for_publish"

        return result


# ── MCP 工具定义 ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "publish_markdown",
        "description": "【基础回退】直接转换 Markdown 并创建草稿，排版较基础。需要美观排版时必须先用 gzh-design，再调用 create_draft_from_html_file。"
                       "支持本地图片自动上传到微信 CDN。不需要先手动传图。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "本地 Markdown 文件路径（必填，如 ./article.md）",
                },
                "title": {
                    "type": "string",
                    "description": "文章标题（可选，不传则从 Markdown 第一个 # 标题提取）",
                },
                "author": {
                    "type": "string",
                    "description": "作者署名（可选，显示在标题下方）",
                },
                "digest": {
                    "type": "string",
                    "description": "摘要（可选，不传则自动截取正文前 120 字）",
                },
                "publish": {
                    "type": "boolean",
                    "description": "是否直接发布到公众号（默认 false，只存草稿）",
                },
                "thumb_media_id": {
                    "type": "string",
                    "description": "封面图片 media_id（可选，不传则无封面）",
                },
                "need_open_comment": {
                    "type": "integer",
                    "enum": [0, 1],
                    "description": "是否打开评论（0/1，默认 0）",
                },
                "only_fans_can_comment": {
                    "type": "integer",
                    "enum": [0, 1],
                    "description": "是否仅粉丝可评论（0/1，默认 0）",
                },
                "content_source_url": {
                    "type": "string",
                    "description": "原文链接（可选）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "create_draft_from_html_file",
        "description": "【推荐】读取 gzh-design 生成并校验过的 HTML 文件，保留精美排版创建公众号草稿；仅在 publish=true 时提交发布。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "gzh-design 生成的 HTML 文件路径"},
                "title": {"type": "string", "description": "文章标题"},
                "author": {"type": "string", "description": "作者署名"},
                "digest": {"type": "string", "description": "摘要"},
                "publish": {"type": "boolean", "description": "默认 false，只创建草稿"},
                "thumb_media_id": {"type": "string", "description": "可选封面 media_id"},
                "need_open_comment": {"type": "integer", "enum": [0, 1]},
                "only_fans_can_comment": {"type": "integer", "enum": [0, 1]},
                "content_source_url": {"type": "string", "description": "可选原文链接"}
            },
            "required": ["file_path", "title"]
        }
    },
    {
        "name": "upload_image",
        "description": "上传本地图片到微信 CDN，返回永久 CDN URL。图片会永久保存在微信服务器上。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "本地图片路径（如 ./images/cover.png）",
                },
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "create_draft",
        "description": "用 HTML 正文直接创建图文草稿。优先传入 gzh-design 生成的精美 HTML；文件较大时使用 create_draft_from_html_file。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "文章标题"},
                "content": {"type": "string", "description": "HTML 正文内容"},
                "author": {"type": "string", "description": "作者署名"},
                "digest": {"type": "string", "description": "摘要（不传则自动截取）"},
                "thumb_media_id": {"type": "string", "description": "封面 media_id"},
                "need_open_comment": {"type": "integer", "enum": [0, 1]},
                "only_fans_can_comment": {"type": "integer", "enum": [0, 1]},
            },
            "required": ["title", "content"],
        },
    },
    {
        "name": "update_draft",
        "description": "更新已有草稿。只传需要修改的字段，未传的字段保留原值。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "media_id": {"type": "string", "description": "要更新的草稿 media_id（必填）"},
                "title": {"type": "string", "description": "新的标题"},
                "content": {"type": "string", "description": "新的 HTML 正文"},
                "author": {"type": "string", "description": "新的作者"},
                "digest": {"type": "string", "description": "新的摘要"},
            },
            "required": ["media_id"],
        },
    },
    {
        "name": "publish_draft",
        "description": "将草稿提交发布。提交后微信会在几分钟内完成发布，可在公众号后台查看状态。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "media_id": {"type": "string", "description": "草稿的 media_id（必填）"},
            },
            "required": ["media_id"],
        },
    },
    {
        "name": "list_drafts",
        "description": "列出所有草稿（最近 20 条，不含正文内容）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "offset": {"type": "integer", "description": "偏移量，默认 0"},
                "count": {"type": "integer", "description": "每页条数，默认 20，最大 20"},
                "no_content": {
                    "type": "boolean",
                    "description": "是否不返回正文内容（默认 true 只返回标题摘要）",
                },
            },
        },
    },
    {
        "name": "get_draft",
        "description": "获取单篇草稿的完整详情（含 HTML 正文）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "media_id": {"type": "string", "description": "草稿的 media_id（必填）"},
            },
            "required": ["media_id"],
        },
    },
]


# ── JSON-RPC over stdio ──────────────────────────────────────────────────

def handle_request(wx: WeChatClient | None, req: dict) -> dict | None:
    """处理单条 JSON-RPC 请求。"""
    method = req.get("method")
    rid = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "serverInfo": {"name": "wechat-mp-mcp", "version": "0.1"},
                "capabilities": {"tools": {}},
            },
        }
    if method == "notifications/initialized":
        return None
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = req["params"]["name"]
        tool_args = req["params"].get("arguments", {})

        if wx is None:
            return {
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32000, "message": "WeChat 客户端未初始化，请设置 WECHAT_APPID 和 WECHAT_APPSECRET"},
            }

        handler_map = {
            "publish_markdown": wx.publish_markdown,
            "create_draft_from_html_file": wx.create_draft_from_html_file,
            "upload_image": wx.upload_image,
            "create_draft": wx.create_draft,
            "update_draft": wx.update_draft,
            "publish_draft": wx.publish_draft,
            "list_drafts": wx.list_drafts,
            "get_draft": wx.get_draft,
        }
        handler = handler_map.get(tool_name)
        if not handler:
            return {
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"未知工具: {tool_name}"},
            }
        try:
            result = handler(**tool_args)
            text = json.dumps(result, ensure_ascii=False, indent=2)
            return {
                "jsonrpc": "2.0", "id": rid,
                "result": {"content": [{"type": "text", "text": text}]},
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32000, "message": str(e)},
            }

    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "method not found"}}


def main() -> None:
    """MCP server 主循环：从 stdin 读 JSON-RPC 请求，处理，写回 stdout。

    首次调用 WeChat API 时初始化 WeChatClient（懒加载），避免 tools/list 等
    无认证请求被阻塞。
    """
    wx: WeChatClient | None = None

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)

        # tools/call 时才可能初始化 WeChatClient，懒加载
        if req.get("method") == "tools/call" and wx is None:
            try:
                config = _get_config()
                wx = WeChatClient(config["appid"], config["secret"])
            except RuntimeError as e:
                # 不在这里抛，让 handle_request 返回 error 响应
                pass

        resp = handle_request(wx, req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
