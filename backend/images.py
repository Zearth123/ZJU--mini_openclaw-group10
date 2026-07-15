"""Image preparation helpers for multimodal user messages."""
from __future__ import annotations

import base64                                                  # 图片 base64 编码
import io                                                      # 内存中的字节流
import mimetypes                                              # 根据扩展名猜 MIME 类型
from pathlib import Path
from typing import Any


# 图片最大边长，超过此值会做缩略
MAX_IMAGE_EDGE = 1568


# 将本地图片转为 base64 编码的内容块，用于多模态消息
# 大图自动缩略以减少 token 消耗
def image_block(path: str | Path, media_type: str | None = None) -> dict[str, Any]:
    """Return an Anthropic-style base64 image block, resizing large images."""
    from PIL import Image, ImageOps

    image_path = Path(path)
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")

    # 猜测 MIME 类型：优先使用传入参数，其次根据扩展名推断，最后默认 PNG
    guessed_type = media_type or mimetypes.guess_type(image_path.name)[0] or "image/png"
    if not guessed_type.startswith("image/"):
        raise ValueError(f"不是支持的图片类型：{guessed_type}")

    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened)         # 根据 EXIF 方向信息自动旋转
        should_resize = max(image.size) > MAX_IMAGE_EDGE
        if should_resize:
            image = image.copy()
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)  # 等比例缩略

        if should_resize:
            # 缩略后的图片编码到内存字节流，避免写磁盘
            output = io.BytesIO()
            output_type, output_format = _output_format(guessed_type)
            if output_format == "JPEG" and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")  # RGBA/调色板模式转 RGB 才能存 JPEG
            image.save(output, format=output_format, optimize=True)
            raw = output.getvalue()
            guessed_type = output_type
        else:
            raw = image_path.read_bytes()      # 未缩略时直接读原始字节

    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": guessed_type,
            "data": encoded,
        },
    }


# 构建多模态用户消息：纯文本，或文本+图片列表
def user_content(text: str, image_paths: list[str] | None = None) -> str | list[dict[str, Any]]:
    """Build plain text content or a text/image content-block list."""
    if not image_paths:
        return text                          # 无图片时直接返回纯文本
    # 有图片时返回 content block 列表：第一块是文本，后续每张图片一块
    return [
        {"type": "text", "text": text},
        *(image_block(path) for path in image_paths),
    ]


def _output_format(media_type: str) -> tuple[str, str]:
    if media_type in {"image/jpeg", "image/jpg"}:
        return "image/jpeg", "JPEG"
    if media_type == "image/webp":
        return "image/webp", "WEBP"
    return "image/png", "PNG"
