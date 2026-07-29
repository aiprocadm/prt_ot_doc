"""OPS-71 срез-1 (разд. 71.1): формат-парсеры импорта.

Что закрепляется:

* три формата (XLSX / CSV / JSON) дают ОДИН и тот же промежуточный вид — иначе
  правила валидации пришлось бы писать трижды;
* CSV из Excel (с BOM) читается: без этого первый заголовок не находится
  маппингом, и пользователь получает «нет обязательной колонки» на файле,
  который он только что скачал шаблоном;
* **XLSX проходит через гард безопасных архивов (SEC-64, разд. 64.2)** — это
  ZIP, который открывает наш код, а гард стоял только на загрузке файлов в
  модуле files, мимо которого этот путь идёт;
* потолок строк — ОТКАЗ, а не тихое усечение: импортировать половину файла и
  отчитаться успехом хуже, чем не импортировать вовсе.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from app.modules.imports.parsers import (
    MAX_IMPORT_ROWS,
    ImportFileError,
    parse_import_file,
)

CSV_BODY = "Табельный номер,Фамилия,Имя\n001,Иванов,Иван\n002,Петров,Пётр\n"


def _xlsx(rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestFormats:
    def test_csv_with_excel_bom_is_readable(self) -> None:
        parsed = parse_import_file("staff.csv", ("﻿" + CSV_BODY).encode("utf-8"))

        assert parsed.headers[0] == "Табельный номер"
        assert len(parsed.rows) == 2
        assert parsed.rows[0]["Фамилия"] == "Иванов"

    def test_blank_rows_are_dropped(self) -> None:
        parsed = parse_import_file("staff.csv", (CSV_BODY + ",,\n").encode("utf-8"))

        assert len(parsed.rows) == 2

    def test_xlsx_matches_csv_shape(self) -> None:
        content = _xlsx([["Табельный номер", "Фамилия", "Имя"], ["001", "Иванов", "Иван"]])

        parsed = parse_import_file("staff.xlsx", content)

        assert parsed.headers == ["Табельный номер", "Фамилия", "Имя"]
        assert parsed.rows[0]["Фамилия"] == "Иванов"

    def test_json_accepts_bare_list_and_rows_wrapper(self) -> None:
        payload = [{"Фамилия": "Иванов", "Имя": "Иван"}]

        bare = parse_import_file("staff.json", json.dumps(payload).encode("utf-8"))
        wrapped = parse_import_file("staff.json", json.dumps({"rows": payload}).encode("utf-8"))

        assert bare.rows == wrapped.rows
        assert bare.headers == ["Фамилия", "Имя"]

    def test_unsupported_extension_is_rejected(self) -> None:
        with pytest.raises(ImportFileError) as excinfo:
            parse_import_file("staff.docx", b"whatever")

        assert excinfo.value.code == "import_format_unsupported"

    def test_broken_json_reports_a_readable_error(self) -> None:
        with pytest.raises(ImportFileError) as excinfo:
            parse_import_file("staff.json", b"{not json")

        assert excinfo.value.code == "import_file_unreadable"


class TestGuards:
    def test_row_cap_refuses_instead_of_truncating(self) -> None:
        body = "Фамилия\n" + "".join(f"Иванов{i}\n" for i in range(MAX_IMPORT_ROWS + 1))

        with pytest.raises(ImportFileError) as excinfo:
            parse_import_file("staff.csv", body.encode("utf-8"))

        assert excinfo.value.code == "import_file_too_many_rows"
        # Число в сообщении обязательно: «слишком много строк» без предела не
        # подсказывает, на сколько частей резать файл.
        assert str(MAX_IMPORT_ROWS) in excinfo.value.message

    def test_macro_bearing_xlsx_is_rejected_by_content_not_extension(self) -> None:
        """Переименованный .xlsm не должен снимать проверку (находка SEC-64)."""

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("xl/workbook.xml", "<workbook/>")
            archive.writestr("xl/vbaProject.bin", b"\x00\x01")

        with pytest.raises(ImportFileError) as excinfo:
            parse_import_file("staff.xlsx", buffer.getvalue())

        assert excinfo.value.code == "archive_macro_enabled"

    def test_legitimate_xlsx_still_passes_the_archive_guard(self) -> None:
        """Гард, мешающий обычной работе, отключат при первой жалобе."""

        parsed = parse_import_file("staff.xlsx", _xlsx([["Фамилия"], ["Иванов"]]))

        assert parsed.rows[0]["Фамилия"] == "Иванов"
