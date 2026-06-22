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
    regex: bool = False
    normalize_runs: bool = True
    ignore_styles: list[str] | None = None
    ignore_regex: list[str] | None = None


@dataclass
class ReplaceHit:
    from_text: str
    to_text: str
    part: str
    location: str
    before: str
    after: str
    context: str
    match_count: int


@dataclass
class ReplaceResult:
    docx_bytes: bytes
    hits: list[ReplaceHit]


_WORD = r"(?<![0-9A-Za-zА-Яа-яЁё_]){value}(?![0-9A-Za-zА-Яа-яЁё_])"


def _iter_paragraphs(container: object, prefix: str):
    if hasattr(container, "paragraphs"):
        for i, p in enumerate(getattr(container, "paragraphs")):
            yield p, f"{prefix}.p[{i}]"
    if hasattr(container, "tables"):
        for t_i, table in enumerate(getattr(container, "tables")):
            for r_i, row in enumerate(table.rows):
                for c_i, cell in enumerate(row.cells):
                    yield from _iter_paragraphs(cell, f"{prefix}.tbl[{t_i}].r[{r_i}].c[{c_i}]")


def _style_ignored(paragraph: Paragraph, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    style_name = getattr(getattr(paragraph, "style", None), "name", "") or ""
    if not style_name:
        return False
    escaped = [re.escape(x).replace(r"\*", ".*") for x in patterns]
    return any(re.fullmatch(p, style_name) for p in escaped)


def _normalize_runs(paragraph: Paragraph) -> None:
    if len(paragraph.runs) < 2:
        return
    merged = [paragraph.runs[0]]
    for run in paragraph.runs[1:]:
        prev = merged[-1]
        if prev._r.rPr is not None and run._r.rPr is not None and prev._r.rPr.xml == run._r.rPr.xml:
            prev.text += run.text
            paragraph._element.remove(run._element)
        else:
            merged.append(run)


def _pattern(source: str, options: ReplaceOptions) -> re.Pattern[str]:
    value = source if options.regex else re.escape(source)
    if options.whole_word:
        value = _WORD.format(value=value)
    flags = 0 if options.case_sensitive else re.IGNORECASE
    return re.compile(value, flags)


def _ignored_by_regex(text: str, ignore_regex: list[str] | None) -> bool:
    if not ignore_regex:
        return False
    return any(re.search(pattern, text) for pattern in ignore_regex)


def _apply_text_replace(
    text: str, mapping: dict[str, str], options: ReplaceOptions, *, part: str, location: str
) -> tuple[str, list[ReplaceHit]]:
    current = text
    hits: list[ReplaceHit] = []
    if _ignored_by_regex(current, options.ignore_regex):
        return current, hits
    for source, target in mapping.items():
        if not source:
            continue
        p = _pattern(source, options)
        count = len(p.findall(current))
        if count == 0:
            continue
        replaced = p.sub(target, current)
        hits.append(
            ReplaceHit(
                from_text=source,
                to_text=target,
                part=part,
                location=location,
                before=current,
                after=replaced,
                context=current[:120],
                match_count=count,
            )
        )
        current = replaced
    return current, hits


def _replace_shapes(
    docx_bytes: bytes, mapping: dict[str, str], options: ReplaceOptions
) -> tuple[bytes, list[ReplaceHit]]:
    src = BytesIO(docx_bytes)
    dst = BytesIO()
    hits: list[ReplaceHit] = []
    with ZipFile(src, "r") as zin, ZipFile(dst, "w", ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            payload = zin.read(info.filename)
            if info.filename.startswith("word/") and info.filename.endswith(".xml"):
                try:
                    text = payload.decode("utf-8")
                except UnicodeDecodeError:
                    zout.writestr(info, payload)
                    continue
                if "txbxContent" in text or "<v:textbox" in text:
                    updated, local = _apply_text_replace(
                        text, mapping, options, part="shape", location=info.filename
                    )
                    hits.extend(local)
                    payload = updated.encode("utf-8")
            zout.writestr(info, payload)
    return dst.getvalue(), hits


def replace_docx_bytes(
    docx_bytes: bytes,
    mapping: dict[str, str],
    options: ReplaceOptions,
    *,
    apply_changes: bool = True,
) -> ReplaceResult:
    doc = Document(BytesIO(docx_bytes))
    hits: list[ReplaceHit] = []
    for paragraph, path in _iter_paragraphs(doc, "body"):
        if _style_ignored(paragraph, options.ignore_styles):
            continue
        if options.normalize_runs:
            _normalize_runs(paragraph)
        current = paragraph.text
        replaced, local = _apply_text_replace(current, mapping, options, part="body", location=path)
        if apply_changes and replaced != current:
            paragraph.text = replaced
        hits.extend(local)

    for idx, sec in enumerate(doc.sections):
        for paragraph, path in _iter_paragraphs(sec.header, f"hdr[{idx}]"):
            if options.normalize_runs:
                _normalize_runs(paragraph)
            current = paragraph.text
            replaced, local = _apply_text_replace(
                current, mapping, options, part="header", location=path
            )
            if apply_changes and replaced != current:
                paragraph.text = replaced
            hits.extend(local)
        for paragraph, path in _iter_paragraphs(sec.footer, f"ftr[{idx}]"):
            if options.normalize_runs:
                _normalize_runs(paragraph)
            current = paragraph.text
            replaced, local = _apply_text_replace(
                current, mapping, options, part="footer", location=path
            )
            if apply_changes and replaced != current:
                paragraph.text = replaced
            hits.extend(local)

    out = BytesIO()
    doc.save(out)
    data = out.getvalue() if apply_changes else docx_bytes
    shape_bytes, shape_hits = _replace_shapes(data, mapping, options)
    hits.extend(shape_hits)
    return ReplaceResult(docx_bytes=shape_bytes if apply_changes else docx_bytes, hits=hits)
