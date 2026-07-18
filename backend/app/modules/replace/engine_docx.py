from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from docx import Document
from docx.text.paragraph import Paragraph

from app.modules.replace.normalizer import normalize_paragraph_runs


@dataclass
class Hit:
    location: str
    rule_from: str
    rule_to: str
    before: str
    after: str


def _iter_paragraphs(container: object, prefix: str):
    if not container:
        return
    if hasattr(container, "paragraphs"):
        for idx, p in enumerate(getattr(container, "paragraphs")):
            yield p, f"{prefix}:P[{idx}]"
    if hasattr(container, "tables"):
        for t_i, table in enumerate(getattr(container, "tables")):
            for r_i, row in enumerate(table.rows):
                for c_i, cell in enumerate(row.cells):
                    yield from _iter_paragraphs(cell, f"{prefix}:Table[{t_i}]R[{r_i}]C[{c_i}]")


def _word_pattern(source: str, whole_word: bool, case_sensitive: bool) -> re.Pattern[str]:
    escaped = re.escape(source)
    if whole_word:
        escaped = rf"(?<![0-9A-Za-zА-Яа-яЁё_]){escaped}(?![0-9A-Za-zА-Яа-яЁё_])"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(escaped, flags)


def replace_docx(
    docx_bytes: bytes, rules: list[dict], *, case_sensitive: bool, whole_word: bool
) -> tuple[bytes, list[Hit]]:
    doc = Document(BytesIO(docx_bytes))
    hits: list[Hit] = []

    locations: list[tuple[Paragraph, str]] = list(_iter_paragraphs(doc, "body"))
    for s_idx, section in enumerate(doc.sections):
        locations.extend(_iter_paragraphs(section.header, f"hdr[{s_idx}]") or [])
        locations.extend(_iter_paragraphs(section.footer, f"ftr[{s_idx}]") or [])

    for paragraph, location in locations:
        normalize_paragraph_runs(paragraph)
        text = "".join(run.text for run in paragraph.runs) if paragraph.runs else paragraph.text
        original = text
        for rule in rules:
            src = str(rule.get("from", ""))
            dst = str(rule.get("to", ""))
            if not src:
                continue
            pattern = _word_pattern(src, whole_word, case_sensitive)
            replaced = pattern.sub(dst, text)
            if replaced != text:
                hits.append(
                    Hit(
                        location=location,
                        rule_from=src,
                        rule_to=dst,
                        before=text[:220],
                        after=replaced[:220],
                    )
                )
                text = replaced
        if text != original:
            if paragraph.runs:
                paragraph.runs[0].text = text
            else:
                paragraph.text = text
    out = BytesIO()
    doc.save(out)
    return out.getvalue(), hits
