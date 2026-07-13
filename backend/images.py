"""Image preparation helpers for multimodal user messages."""
from __future__ import annotations

import base64
import io
import mimetypes
from pathlib import Path
from typing import Any


MAX_IMAGE_EDGE = 1568


def image_block(path: str | Path, media_type: str | None = None) -> dict[str, Any]:
    """Return an Anthropic-style base64 image block, resizing large images."""
    from PIL import Image, ImageOps

    image_path = Path(path)
    if not image_path.is_file():
        raise FileNotFoundError(f"图片不存在：{image_path}")

    guessed_type = media_type or mimetypes.guess_type(image_path.name)[0] or "image/png"
    if not guessed_type.startswith("image/"):
        raise ValueError(f"不是支持的图片类型：{guessed_type}")

    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened)
        should_resize = max(image.size) > MAX_IMAGE_EDGE
        if should_resize:
            image = image.copy()
            image.thumbnail((MAX_IMAGE_EDGE, MAX_IMAGE_EDGE), Image.Resampling.LANCZOS)

        if should_resize:
            output = io.BytesIO()
            output_type, output_format = _output_format(guessed_type)
            if output_format == "JPEG" and image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            image.save(output, format=output_format, optimize=True)
            raw = output.getvalue()
            guessed_type = output_type
        else:
            raw = image_path.read_bytes()

    encoded = base64.b64encode(raw).decode("ascii")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": guessed_type,
            "data": encoded,
        },
    }


def user_content(text: str, image_paths: list[str] | None = None) -> str | list[dict[str, Any]]:
    """Build plain text content or a text/image content-block list."""
    if not image_paths:
        return text
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
