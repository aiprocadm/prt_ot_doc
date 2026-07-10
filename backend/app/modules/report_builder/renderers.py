"""Render ReportResult rows to CSV / XLSX / PDF bytes.

PDF: python-docx таблица (landscape A4) → LibreOffice pool (тот же конвейер,
что печатные формы medical/sout). LibreOffice недоступен → типизированный
``PdfRendererUnavailable`` — материализатор переводит job в failed с кодом
``pdf_renderer_unavailable`` (страница показывает понятную ошибку).
Конвертер вынесен в module-level ``_convert_docx_to_pdf`` для подмены в юнитах.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timezone

from app.modules.report_builder.engine import ReportResult

CSV_MEDIA = "text/csv"
XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PDF_MEDIA = "application/pdf"
_PDF_TIMEOUT_S = 45

__all__ = [
    "CSV_MEDIA",
    "XLSX_MEDIA",
    "PDF_MEDIA",
    "PdfRendererUnavailable",
    "render_csv",
    "render_xlsx",
    "render_pdf",
]


class PdfRendererUnavailable(Exception):
    """LibreOffice pool отсутствует/упал — PDF сейчас недоступен."""


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "да" if value else "нет"
    return str(value)


def render_csv(result: ReportResult) -> bytes:
    buff = io.StringIO()
    writer = csv.writer(buff, delimiter=";", lineterminator="\r\n")
    writer.writerow([c.label for c in result.columns])
    for row in result.rows:
        writer.writerow([_cell(row.get(c.key)) for c in result.columns])
    # BOM: иначе Excel-RU открывает UTF-8 как кракозябры
    return ("﻿" + buff.getvalue()).encode("utf-8")


def _sheet_title(title: str) -> str:
    # Excel: max 31 символ, запрещены []:*?/\
    clean = re.sub(r"[\[\]:*?/\\]", " ", title or "Отчёт").strip() or "Отчёт"
    return clean[:31]


def render_xlsx(result: ReportResult, *, title: str) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = _sheet_title(title)
    ws.append([c.label for c in result.columns])
    for row in result.rows:
        ws.append(
            [
                (
                    ("да" if row[c.key] else "нет")
                    if isinstance(row.get(c.key), bool)
                    else row.get(c.key)
                )
                for c in result.columns
            ]
        )
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _build_docx_table(result: ReportResult, *, title: str) -> bytes:
    from docx import Document
    from docx.enum.section import WD_ORIENT

    doc = Document()
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    doc.add_heading(title or "Отчёт", level=1)
    generated = datetime.now(tz=timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
    doc.add_paragraph(f"Сформировано: {generated} · строк: {len(result.rows)}")
    table = doc.add_table(rows=1, cols=max(len(result.columns), 1))
    table.style = "Table Grid"
    for i, col in enumerate(result.columns):
        table.rows[0].cells[i].text = col.label
    for row in result.rows:
        cells = table.add_row().cells
        for i, col in enumerate(result.columns):
            cells[i].text = _cell(row.get(col.key))
    buff = io.BytesIO()
    doc.save(buff)
    return buff.getvalue()


def _convert_docx_to_pdf(*, source_bytes: bytes) -> bytes:
    # Импорт внутри: LibreOffice-стек не нужен ни CSV/XLSX-пути, ни юнитам
    from app.modules.pdf.convert import convert_docx_bytes
    from app.modules.pdf.service_pool import LibreOfficePool

    pdf_bytes, _sha = convert_docx_bytes(
        source_bytes=source_bytes,
        timeout_s=_PDF_TIMEOUT_S,
        pool=LibreOfficePool(),
        passport=None,
    )
    return pdf_bytes


def render_pdf(result: ReportResult, *, title: str) -> bytes:
    docx_bytes = _build_docx_table(result, title=title)
    try:
        return _convert_docx_to_pdf(source_bytes=docx_bytes)
    except Exception as exc:  # soffice отсутствует / таймаут / сбой конвертации
        raise PdfRendererUnavailable(str(exc)) from exc
