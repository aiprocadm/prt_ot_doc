from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from docx import Document
from docx.text.paragraph import Paragraph


@dataclass
class ReplaceOptions:
    case_sensitive: bool = False
    whole_word: bool = False
    include_headers: bool = True
    include_footers: bool = True
    include_shapes: bool = True


@dataclass
class ReplaceDiffItem:
    path: str
    from_text: str
    to_text: str
    occurrences: int
    context_before: str
    context_after: str
    section: str


@dataclass
class ReplaceResult:
    docx_bytes: bytes
    items: list[ReplaceDiffItem]


_WORD = r"(?<![0-9A-Za-zА-Яа-яЁё_]){value}(?![0-9A-Za-zА-Яа-яЁё_])"


def _iter_paragraphs(container: object, prefix: str):
    if hasattr(container, "paragraphs"):
        for i, p in enumerate(getattr(container, "paragraphs")):
            yield p, f"{prefix}.p[{i}]", prefix
    if hasattr(container, "tables"):
        for t_i, table in enumerate(getattr(container, "tables")):
            for r_i, row in enumerate(table.rows):
                for c_i, cell in enumerate(row.cells):
                    yield from _iter_paragraphs(cell, f"{prefix}.tbl[{t_i}].r[{r_i}].c[{c_i}]")


def _normalize_runs(paragraph: Paragraph) -> None:
    if len(paragraph.runs) < 2:
        return
    paragraph.runs[0].text = "".join(run.text for run in paragraph.runs)
    for run in list(paragraph.runs)[1:]:
        paragraph._element.remove(run._element)


def _pattern(source: str, options: ReplaceOptions) -> re.Pattern[str]:
    value = re.escape(source)
    if options.whole_word:
        value = _WORD.format(value=value)
    flags = 0 if options.case_sensitive else re.IGNORECASE
    return re.compile(value, flags)


def _apply_text_replace(text: str, mapping: dict[str, str], options: ReplaceOptions, path: str, section: str) -> tuple[str, list[ReplaceDiffItem]]:
    current = text
    items: list[ReplaceDiffItem] = []
    for source, target in mapping.items():
        if not source:
            continue
        p = _pattern(source, options)
        count = len(p.findall(current))
        if count == 0:
            continue
        replaced = p.sub(target, current)
        items.append(
            ReplaceDiffItem(
                path=path,
                from_text=source,
                to_text=target,
                occurrences=count,
                context_before=current[:180],
                context_after=replaced[:180],
                section=section,
            )
        )
        current = replaced
    return current, items


def _replace_shapes(docx_bytes: bytes, mapping: dict[str, str], options: ReplaceOptions) -> tuple[bytes, list[ReplaceDiffItem]]:
    if not options.include_shapes:
        return docx_bytes, []
    src = BytesIO(docx_bytes)
    dst = BytesIO()
    items: list[ReplaceDiffItem] = []
    with ZipFile(src, "r") as zin, ZipFile(dst, "w", ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            payload = zin.read(info.filename)
            if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                try:
                    text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(info, payload)
                    continue
                if "txbxContent" in text or "<v:shape" in text:
                    updated, local = _apply_text_replace(text, mapping, options, path=f"shape:{info.filename}", section="shape")
                    items.extend(local)
                    payload = updated.encode("utf-8")
            zout.writestr(info, payload)
    return dst.getvalue(), items


def replace_docx_bytes(docx_bytes: bytes, mapping: dict[str, str], options: ReplaceOptions) -> ReplaceResult:
    doc = Document(BytesIO(docx_bytes))
    items: list[ReplaceDiffItem] = []
    for paragraph, path, section in _iter_paragraphs(doc, "body"):
        _normalize_runs(paragraph)
        current = paragraph.text
        replaced, local = _apply_text_replace(current, mapping, options, path, section)
        if replaced != current:
            paragraph.text = replaced
        items.extend(local)

    for idx, sec in enumerate(doc.sections):
        if options.include_headers:
            for paragraph, path, section in _iter_paragraphs(sec.header, f"hdr[{idx}]"):
                _normalize_runs(paragraph)
                current = paragraph.text
                replaced, local = _apply_text_replace(current, mapping, options, path, "header")
                if replaced != current:
                    paragraph.text = replaced
                items.extend(local)
        if options.include_footers:
            for paragraph, path, section in _iter_paragraphs(sec.footer, f"ftr[{idx}]"):
                _normalize_runs(paragraph)
                current = paragraph.text
                replaced, local = _apply_text_replace(current, mapping, options, path, "footer")
                if replaced != current:
                    paragraph.text = replaced
                items.extend(local)

    out = BytesIO()
    doc.save(out)
    shape_bytes, shape_items = _replace_shapes(out.getvalue(), mapping, options)
    items.extend(shape_items)
    return ReplaceResult(docx_bytes=shape_bytes, items=items)
