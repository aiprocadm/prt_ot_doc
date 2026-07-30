"""Импорт отчёта СОУТ обязан проверять XLSX как архив (SEC-64, разд. 64.2).

Дефект, найденный в волне OPS-71: XLSX — это ZIP, и распаковывает его наш
процесс, а гард `assert_safe_office_archive` стоял ТОЛЬКО на финализации
загрузки в модуле `files`. Ручки `/sout/{cid}/import/*` туда не заходят, то есть
zip-бомба и макрос-контейнер попадали прямо в openpyxl мимо всей защиты.
Обход через переименование `.xlsm` → `.xlsx` работал бы и здесь — ровно тот,
который SEC-64 уже закрывал в другом месте.

Отдельно закрепляется, что легитимный XLSX по-прежнему разбирается: гард,
мешающий обычной работе, отключат при первой жалобе.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.core.archive_safety import ArchiveSafetyError
from app.domains.sout.import_report import parse_report, parse_xlsx


def _valid_xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Код РМ", "Должность", "Класс"])
    sheet.append(["РМ-01", "Слесарь", "3.1"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _macro_bearing_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/workbook.xml", "<workbook/>")
        archive.writestr("xl/vbaProject.bin", b"\x00\x01")
    return buffer.getvalue()


def test_macro_bearing_workbook_is_rejected_by_content() -> None:
    with pytest.raises(ArchiveSafetyError) as excinfo:
        parse_xlsx(_macro_bearing_zip())

    assert excinfo.value.code == "archive_macro_enabled"


def test_rejection_also_applies_through_the_format_dispatcher() -> None:
    """Переименование в `.xlsx` не должно снимать проверку."""

    with pytest.raises(ArchiveSafetyError):
        parse_report(_macro_bearing_zip(), "otchet.xlsx")


def test_path_traversal_entry_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../../etc/passwd", "x")

    with pytest.raises(ArchiveSafetyError) as excinfo:
        parse_xlsx(buffer.getvalue())

    assert excinfo.value.code == "archive_path_traversal"


def test_legitimate_report_still_parses() -> None:
    parsed = parse_report(_valid_xlsx(), "otchet.xlsx")

    assert [wp.workplace_code for wp in parsed] == ["РМ-01"]
