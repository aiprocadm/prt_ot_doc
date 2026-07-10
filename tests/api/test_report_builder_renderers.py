"""Renderers: CSV (;+BOM), XLSX round-read, PDF graceful unavailability."""

from __future__ import annotations

import io

import pytest

from app.modules.report_builder.engine import ColumnMeta, ReportResult

RESULT = ReportResult(
    columns=[
        ColumnMeta(key="name", label="Название", kind="string"),
        ColumnMeta(key="qty", label="Кол-во", kind="number"),
        ColumnMeta(key="flag", label="Просрочено", kind="bool"),
    ],
    rows=[
        {"name": 'ООО "Ромашка"; цех', "qty": 5, "flag": True},
        {"name": "Пила", "qty": None, "flag": False},
    ],
    total=2,
)


def test_csv_semicolon_bom_escaping() -> None:
    from app.modules.report_builder.renderers import render_csv

    body = render_csv(RESULT)
    text = body.decode("utf-8")
    assert text.startswith("﻿")  # BOM для Excel-RU
    lines = text.lstrip("﻿").split("\r\n")
    assert lines[0] == "Название;Кол-во;Просрочено"
    # ячейка с ; и кавычками — заэкранирована стандартным csv-модулем
    assert lines[1] == '"ООО ""Ромашка""; цех";5;да'
    assert lines[2] == "Пила;;нет"


def test_xlsx_round_read() -> None:
    from openpyxl import load_workbook

    from app.modules.report_builder.renderers import render_xlsx

    body = render_xlsx(RESULT, title="Тест [отчёт]")
    wb = load_workbook(io.BytesIO(body))
    ws = wb.active
    # квадратные скобки удалены санитайзером имени листа, длина ≤31
    assert "[" not in ws.title and "]" not in ws.title
    assert len(ws.title) <= 31
    assert [c.value for c in ws[1]] == ["Название", "Кол-во", "Просрочено"]
    assert ws.cell(row=2, column=2).value == 5
    assert ws.cell(row=2, column=3).value == "да"


def test_pdf_unavailable_raises_typed() -> None:
    import app.modules.report_builder.renderers as renderers

    def _boom(**kwargs):
        raise RuntimeError("no soffice")

    orig = renderers._convert_docx_to_pdf
    renderers._convert_docx_to_pdf = _boom  # type: ignore[assignment]
    try:
        with pytest.raises(renderers.PdfRendererUnavailable):
            renderers.render_pdf(RESULT, title="Тест")
    finally:
        renderers._convert_docx_to_pdf = orig  # type: ignore[assignment]


def test_pdf_builds_docx_before_convert() -> None:
    """DOCX-часть строится без LibreOffice — конвертер мокаем на identity."""
    import app.modules.report_builder.renderers as renderers

    captured: dict[str, bytes] = {}

    def _fake(*, source_bytes: bytes, **kwargs) -> bytes:
        captured["docx"] = source_bytes
        return b"%PDF-fake"

    orig = renderers._convert_docx_to_pdf
    renderers._convert_docx_to_pdf = _fake  # type: ignore[assignment]
    try:
        body = renderers.render_pdf(RESULT, title="Тест")
    finally:
        renderers._convert_docx_to_pdf = orig  # type: ignore[assignment]
    assert body == b"%PDF-fake"
    # DOCX действительно собран (zip-магия PK)
    assert captured["docx"][:2] == b"PK"


def test_formula_injection_neutralized() -> None:
    from openpyxl import load_workbook

    from app.modules.report_builder.renderers import render_csv, render_xlsx

    hostile = ReportResult(
        columns=[ColumnMeta(key="name", label="Название", kind="string")],
        rows=[
            {"name": '=HYPERLINK("http://evil")'},
            {"name": "@cmd"},
            {"name": "обычный текст"},
        ],
        total=3,
    )
    csv_text = render_csv(hostile).decode("utf-8")
    assert "'=HYPERLINK" in csv_text and "'@cmd" in csv_text
    wb = load_workbook(io.BytesIO(render_xlsx(hostile, title="x")))
    ws = wb.active
    # ни одна ячейка не стала живой формулой (CWE-1236)
    assert all(ws.cell(row=r, column=1).data_type != "f" for r in (2, 3, 4))
    # содержимое не потеряно: апостроф-префикс для опасных, обычный текст нетронут
    assert ws.cell(row=2, column=1).value == '\'=HYPERLINK("http://evil")'
    assert ws.cell(row=3, column=1).value == "'@cmd"
    assert ws.cell(row=4, column=1).value == "обычный текст"
