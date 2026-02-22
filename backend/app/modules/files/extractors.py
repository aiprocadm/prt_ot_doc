from __future__ import annotations

import re
from pathlib import Path


def normalize_text(text: str) -> str:
    cleaned = (text or "").replace("\x00", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def extract_text_pdf(path: Path) -> str:
    parts: list[str] = []
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        for page in reader.pages:
            parts.append(page.extract_text() or "")
    except Exception:
        try:
            from pdfminer.high_level import extract_text

            parts.append(extract_text(str(path)) or "")
        except Exception:
            return ""

    return normalize_text("\n".join(parts))


def extract_text_docx(path: Path) -> str:
    try:
        from docx import Document
    except Exception:
        return ""
    doc = Document(str(path))
    parts = [p.text for p in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.extend(cell.text for cell in row.cells)
    for section in doc.sections:
        parts.extend(p.text for p in section.header.paragraphs)
        parts.extend(p.text for p in section.footer.paragraphs)
    return normalize_text("\n".join(parts))
