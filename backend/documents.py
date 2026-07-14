"""文档文本提取工具：从 PDF 或 Word（.docx）文件中提取纯文本。

依赖：
  - PyMuPDF (fitz)  → PDF
  - python-docx      → .docx

用法:
  text = extract_document_text("report.pdf")
  text = extract_document_text("report.docx")
"""
from __future__ import annotations

from pathlib import Path


def extract_text_from_pdf(path: str | Path) -> str:
    """使用 PyMuPDF 提取 PDF 文件中的文本，每页用换行分隔。"""
    import fitz  # PyMuPDF

    doc = fitz.open(str(path))
    pages: list[str] = []
    for page in doc:
        text = page.get_text()
        if text.strip():
            pages.append(text)
    doc.close()
    return "\n".join(pages)


def extract_text_from_docx(path: str | Path) -> str:
    """使用 python-docx 提取 Word 文档中的段落文本。"""
    from docx import Document

    doc = Document(str(path))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def extract_document_text(path: str | Path) -> str:
    """自动检测文件扩展名并提取文本。支持 .pdf 和 .docx。"""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"文档不存在：{path}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(path)
    elif suffix in {".docx", ".doc"}:
        return extract_text_from_docx(path)
    else:
        raise ValueError(
            f"不支持的文件格式：{suffix}，当前仅支持 .pdf 和 .docx。"
        )
