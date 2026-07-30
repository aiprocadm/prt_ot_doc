"""OPS-71 (разд. 71.1): формат-парсеры импорта — XLSX / CSV / JSON.

Все три формата сходятся к ОДНОМУ промежуточному виду ``ParsedFile``: список
заголовков (в исходном написании — их показывает мастер маппинга) и список строк
``{заголовок: сырое значение}``. Дальше вся логика (маппинг, валидация, diff,
запись) формат-независима — иначе третий формат означал бы третью копию правил.

Значения НЕ приводятся к типам здесь: приведение зависит от целевого поля, а поле
известно только после маппинга. Парсер отвечает ровно за «достать таблицу из файла».

**Потолок строк — жёсткий отказ, а не тихое усечение.** Синхронный импорт половины
файла — худший исход: выглядит как успех, а половины данных нет, и повторный
запуск догрузит остаток только при идемпотентном ключе. Асинхронный импорт больших
файлов с прогрессом — отдельный срез (разд. 71.1, строка «Прогресс»).
"""

from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from io import BytesIO, StringIO

from app.core.archive_safety import ArchiveSafetyError, assert_safe_office_archive

__all__ = [
    "MAX_ASYNC_IMPORT_ROWS",
    "MAX_IMPORT_ROWS",
    "open_import_source",
    "ImportFileError",
    "ParsedFile",
    "SUPPORTED_EXTENSIONS",
    "parse_import_file",
]

# Потолок строк ОДНОГО СИНХРОННОГО импорта: столько успевает обработаться внутри
# HTTP-запроса, не упираясь в таймаут прокси.
MAX_IMPORT_ROWS = 5000

# Потолок асинхронного импорта. Фоновый путь читает файл ПОТОКОМ (см.
# ``open_import_source``), поэтому память больше не упирается в размер файла —
# предел остался как защита от бесконечной работы на явно неадекватном вводе, а
# не как следствие «всё в памяти». Отсюда и порядок величины.
MAX_ASYNC_IMPORT_ROWS = 1_000_000

SUPPORTED_EXTENSIONS: tuple[str, ...] = (".xlsx", ".csv", ".json")


class ImportFileError(Exception):
    """Файл нечитаем или не поддерживается. ``code`` уходит в ответ API."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass
class ParsedFile:
    """Таблица, извлечённая из файла любого поддерживаемого формата."""

    headers: list[str] = field(default_factory=list)
    rows: list[dict[str, object]] = field(default_factory=list)


def _clean_header(value: object) -> str:
    return "" if value is None else str(value).strip()


def _is_blank_row(row: dict[str, object]) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in row.values())


def _guard_row_count(count: int, max_rows: int) -> None:
    if count > max_rows:
        hint = (
            "Use the asynchronous import for files of this size."
            if max_rows == MAX_IMPORT_ROWS
            else "Split the file into parts."
        )
        raise ImportFileError(
            "import_file_too_many_rows",
            f"File has {count} data rows, the limit is {max_rows}. {hint}",
        )


def parse_csv(content: bytes, *, max_rows: int = MAX_IMPORT_ROWS) -> ParsedFile:
    # utf-8-sig: Excel сохраняет CSV с BOM, и без этого первый заголовок
    # приезжает как "﻿Табельный номер" и не находится маппингом.
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError("import_file_encoding", "CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(StringIO(text))
    headers = [_clean_header(h) for h in (reader.fieldnames or [])]
    rows: list[dict[str, object]] = []
    for raw in reader:
        row = {_clean_header(k): v for k, v in raw.items() if _clean_header(k)}
        if not _is_blank_row(row):
            rows.append(row)
        _guard_row_count(len(rows), max_rows)
    return ParsedFile(headers=[h for h in headers if h], rows=rows)


def parse_xlsx(content: bytes, *, max_rows: int = MAX_IMPORT_ROWS) -> ParsedFile:
    # XLSX — это ZIP, и открывает его наш код. Гард разд. 64.2 стоит на загрузке
    # файлов в модуле files, а этот путь в него не заходит: без явного вызова
    # zip-бомба и макрос-контейнер приезжали бы в парсер мимо всей защиты.
    try:
        assert_safe_office_archive(content)
    except ArchiveSafetyError as exc:
        raise ImportFileError(exc.code, exc.args[-1] if exc.args else str(exc)) from exc

    from openpyxl import load_workbook  # ленивый импорт (тяжёлый), как в sout_import

    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — openpyxl бросает разнородные ошибки
        raise ImportFileError("import_file_unreadable", "XLSX file is not readable") from exc

    try:
        sheet = workbook.active
        if sheet is None:
            return ParsedFile()
        raw_rows = sheet.iter_rows(values_only=True)
        try:
            header_row = next(raw_rows)
        except StopIteration:
            return ParsedFile()
        headers = [_clean_header(c) for c in header_row]
        rows: list[dict[str, object]] = []
        for raw in raw_rows:
            row = {h: v for h, v in zip(headers, raw) if h}
            if not _is_blank_row(row):
                rows.append(row)
            _guard_row_count(len(rows), max_rows)
    finally:
        # read_only=True держит открытым файловый дескриптор внутри zip —
        # без close() они копятся на каждом импорте.
        workbook.close()
    return ParsedFile(headers=[h for h in headers if h], rows=rows)


def parse_json(content: bytes, *, max_rows: int = MAX_IMPORT_ROWS) -> ParsedFile:
    """Массив объектов ``[{"Табельный номер": "001", ...}, ...]``.

    Объект-обёртка ``{"rows": [...]}`` тоже принимается: так выглядит выгрузка
    большинства систем, и требовать от пользователя руками снять обёртку — способ
    получить обращение в поддержку вместо импорта.
    """

    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportFileError("import_file_unreadable", "JSON file is not readable") from exc

    if isinstance(payload, dict):
        for key in ("rows", "items", "data"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
    if not isinstance(payload, list):
        raise ImportFileError(
            "import_file_shape", 'JSON must be a list of objects (or {"rows": [...]})'
        )

    rows: list[dict[str, object]] = []
    headers: list[str] = []
    for entry in payload:
        if not isinstance(entry, dict):
            raise ImportFileError("import_file_shape", "Every JSON list element must be an object")
        row = {_clean_header(k): v for k, v in entry.items() if _clean_header(k)}
        if _is_blank_row(row):
            continue
        for key in row:
            if key not in headers:
                headers.append(key)
        rows.append(row)
        _guard_row_count(len(rows), max_rows)
    return ParsedFile(headers=headers, rows=rows)


def parse_import_file(
    filename: str, content: bytes, *, max_rows: int = MAX_IMPORT_ROWS
) -> ParsedFile:
    """Выбрать парсер по расширению имени файла."""

    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        return parse_xlsx(content, max_rows=max_rows)
    if name.endswith(".csv"):
        return parse_csv(content, max_rows=max_rows)
    if name.endswith(".json"):
        return parse_json(content, max_rows=max_rows)
    raise ImportFileError(
        "import_format_unsupported",
        f"Unsupported file format: {filename!r}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
    )


# --- потоковое чтение -----------------------------------------------------


def open_import_source(
    filename: str, content: bytes, *, max_rows: int = MAX_ASYNC_IMPORT_ROWS
) -> tuple[list[str], Iterator[dict[str, object]]]:
    """Заголовки + ЛЕНИВЫЙ поток строк файла.

    Отличие от :func:`parse_import_file` принципиальное: строки не собираются в
    список. Файл на сотни тысяч строк не должен целиком лежать в памяти воркера —
    именно это ограничение и держало прежний потолок.

    Заголовки читаются сразу (их нужно знать до маппинга), поэтому возвращаются
    отдельно, а не первым элементом потока: иначе каждый потребитель начинался бы
    с одинакового «пропустить первую строку», и кто-нибудь однажды забыл бы.
    """

    name = (filename or "").lower()
    if name.endswith(".csv"):
        return _stream_csv(content, max_rows)
    if name.endswith(".xlsx"):
        return _stream_xlsx(content, max_rows)
    if name.endswith(".json"):
        # JSON без потоковой библиотеки разбирается целиком по своей природе:
        # массив нельзя читать по одному объекту, не написав свой парсер.
        # Честнее переиспользовать общий разбор, чем делать вид, что он потоковый.
        parsed = parse_json(content, max_rows=max_rows)
        return parsed.headers, iter(parsed.rows)
    raise ImportFileError(
        "import_format_unsupported",
        f"Unsupported file format: {filename!r}. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
    )


def _stream_csv(content: bytes, max_rows: int) -> tuple[list[str], Iterator[dict[str, object]]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ImportFileError("import_file_encoding", "CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(StringIO(text))
    headers = [h for h in (_clean_header(h) for h in (reader.fieldnames or [])) if h]

    def _rows() -> Iterator[dict[str, object]]:
        count = 0
        for raw in reader:
            row = {_clean_header(k): v for k, v in raw.items() if _clean_header(k)}
            if _is_blank_row(row):
                continue
            count += 1
            _guard_row_count(count, max_rows)
            yield row

    return headers, _rows()


def _stream_xlsx(content: bytes, max_rows: int) -> tuple[list[str], Iterator[dict[str, object]]]:
    try:
        assert_safe_office_archive(content)
    except ArchiveSafetyError as exc:
        raise ImportFileError(exc.code, exc.args[-1] if exc.args else str(exc)) from exc

    from openpyxl import load_workbook

    try:
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — openpyxl бросает разнородные ошибки
        raise ImportFileError("import_file_unreadable", "XLSX file is not readable") from exc

    sheet = workbook.active
    if sheet is None:
        workbook.close()
        return [], iter(())
    raw_rows = sheet.iter_rows(values_only=True)
    try:
        header_row = next(raw_rows)
    except StopIteration:
        workbook.close()
        return [], iter(())
    headers_all = [_clean_header(c) for c in header_row]
    headers = [h for h in headers_all if h]

    def _rows() -> Iterator[dict[str, object]]:
        count = 0
        try:
            for raw in raw_rows:
                row = {h: v for h, v in zip(headers_all, raw) if h}
                if _is_blank_row(row):
                    continue
                count += 1
                _guard_row_count(count, max_rows)
                yield row
        finally:
            # Книга закрывается ТОЛЬКО когда поток исчерпан или брошен: read_only
            # держит открытый дескриптор внутри zip, и ранний close оборвал бы чтение.
            workbook.close()

    return headers, _rows()
