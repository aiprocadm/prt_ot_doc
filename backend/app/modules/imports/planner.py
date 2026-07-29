"""OPS-71 (разд. 71.1): маппинг, валидация и план импорта — чистый домен.

Ни одного обращения к БД: на вход приходят разобранный файл, схема маппинга,
уже загруженные справочники и уже найденные существующие записи, на выходе —
план «что будет создано / обновлено / пропущено / отвергнуто». Один и тот же
план строится и для dry-run, и для применения: разойдись они, предпросмотр
перестал бы что-либо гарантировать (та же связка «план = исполнение», что в
офбординге OPS-72).

Ошибки — построчные и с кодом. «Файл не загрузился» без указания строки и причины
заставляет пользователя гадать, а импорт кадров — это сотни строк.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.modules.imports.parsers import ParsedFile
from app.modules.imports.registry import ImportColumn, ImportTarget

__all__ = [
    "ImportPlan",
    "MappingResult",
    "PlannedRow",
    "ResolvedRow",
    "RowError",
    "build_mapping",
    "build_plan",
    "make_key",
    "normalize_header",
    "resolve_rows",
    "template_headers",
]

KEY_SEPARATOR = "\x1f"

_DATE_FORMATS = ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%Y/%m/%d")


def normalize_header(value: object) -> str:
    """Заголовок → сравнимый токен: регистр, ё/е, пробелы и пунктуация не важны.

    Файлы приходят от людей: «Табельный №», «табельный номер», «ТАБЕЛЬНЫЙ  НОМЕР»
    — это одна и та же колонка, и отказ их сопоставить читается как поломка.
    """

    raw = str(value or "")
    # «№» разворачивается ДО NFKC: нормализация превращает его в «No», и
    # «Табельный №» перестаёт быть синонимом «Табельный номер» — заголовок,
    # который в кадровых выгрузках встречается чаще полного слова.
    raw = raw.replace("№", " номер ")
    text = unicodedata.normalize("NFKC", raw).strip().lower()
    text = text.replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _column_tokens(column: ImportColumn) -> set[str]:
    return {normalize_header(column.title), *(normalize_header(a) for a in column.aliases)}


@dataclass
class MappingResult:
    """Схема «поле модели → заголовок файла» и всё, что о ней надо сказать."""

    mapping: dict[str, str] = field(default_factory=dict)
    unmapped_headers: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    # Заголовок, на который претендует несколько колонок цели, или наоборот —
    # признак того, что автоопределение угадало не то. Показывается пользователю.
    ambiguous_headers: list[str] = field(default_factory=list)


def build_mapping(
    target: ImportTarget,
    headers: list[str],
    overrides: dict[str, str] | None = None,
) -> MappingResult:
    """Автоопределение по заголовкам + явные переопределения пользователя.

    ``overrides`` (поле модели → заголовок файла) всегда сильнее автоопределения:
    визуальный маппинг существует именно для случая, когда угадали неверно.
    """

    present = [h for h in headers if str(h).strip()]
    by_token: dict[str, list[str]] = {}
    for header in present:
        by_token.setdefault(normalize_header(header), []).append(header)

    result = MappingResult()
    taken: set[str] = set()

    for column in target.columns:
        chosen: str | None = None
        for token in _column_tokens(column):
            candidates = by_token.get(token)
            if not candidates:
                continue
            if len(candidates) > 1 and candidates[0] not in result.ambiguous_headers:
                result.ambiguous_headers.append(candidates[0])
            chosen = candidates[0]
            break
        if chosen is not None:
            result.mapping[column.field] = chosen
            taken.add(chosen)

    for field_name, header in (overrides or {}).items():
        column = target.column(field_name)
        if column is None or header not in present:
            continue
        previous = result.mapping.get(field_name)
        if previous is not None and previous != header:
            taken.discard(previous)
        result.mapping[field_name] = header
        taken.add(header)

    result.unmapped_headers = [h for h in present if h not in taken]
    result.missing_required = [
        c.title for c in target.columns if c.required and c.field not in result.mapping
    ]
    return result


def template_headers(target: ImportTarget) -> list[str]:
    """Заголовки пустого шаблона — ровно те, что понимает автоопределение."""

    return [c.title + (" *" if c.required else "") for c in target.columns]


@dataclass
class RowError:
    code: str
    message: str
    field: str | None = None


@dataclass
class ResolvedRow:
    """Строка файла после приведения типов и справочников — до сверки с БД."""

    row_number: int
    values: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)
    errors: list[RowError] = field(default_factory=list)
    natural_key: str | None = None
    key_title: str | None = None

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass
class PlannedRow:
    row_number: int
    action: str  # create | update | skip | error
    natural_key: str | None = None
    values: dict[str, Any] = field(default_factory=dict)
    # Прежние значения ИЗМЕНЁННЫХ полей. Без этого снимка «откатить партию»
    # для обновлений невыполнимо: вернуть данные будет не из чего.
    before: dict[str, Any] = field(default_factory=dict)
    entity_id: str | None = None
    errors: list[RowError] = field(default_factory=list)


@dataclass
class ImportPlan:
    rows: list[PlannedRow] = field(default_factory=list)
    mapping: dict[str, str] = field(default_factory=dict)
    unmapped_headers: list[str] = field(default_factory=list)
    # Значения справочников, которых нет в системе: сгруппированы, чтобы
    # пользователь создал их одним заходом, а не ловил построчно.
    unknown_references: dict[str, list[str]] = field(default_factory=dict)

    def counts(self) -> dict[str, int]:
        totals = {"create": 0, "update": 0, "skip": 0, "error": 0}
        for row in self.rows:
            totals[row.action] = totals.get(row.action, 0) + 1
        totals["total"] = len(self.rows)
        return totals


def _coerce_date(raw: Any) -> tuple[date | None, str | None]:
    if isinstance(raw, datetime):
        return raw.date(), None
    if isinstance(raw, date):
        return raw, None
    text = str(raw).strip()
    if not text:
        return None, None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, f"{text!r} is not a date (expected DD.MM.YYYY or YYYY-MM-DD)"


def _coerce_int(raw: Any) -> tuple[int | None, str | None]:
    if isinstance(raw, bool):
        return int(raw), None
    if isinstance(raw, int):
        return raw, None
    text = str(raw).strip()
    if not text:
        return None, None
    try:
        # Excel отдаёт целые как 12.0 — это то же число, а не ошибка ввода.
        return int(float(text.replace(",", "."))), None
    except ValueError:
        return None, f"{text!r} is not a number"


def _coerce_enum(raw: Any, column: ImportColumn) -> tuple[str | None, str | None]:
    text = str(raw or "").strip()
    if not text:
        return None, None
    token = normalize_header(text)
    if token in {normalize_header(v) for v in column.enum_values}:
        return next(v for v in column.enum_values if normalize_header(v) == token), None
    for alias, value in column.enum_aliases.items():
        if normalize_header(alias) == token:
            return value, None
    allowed = ", ".join(column.enum_values)
    return None, f"{text!r} is not one of: {allowed}"


def _stringify(raw: Any) -> str:
    if isinstance(raw, float) and raw.is_integer():
        # Табельный номер из XLSX приезжает как 1001.0 — как строка это уже
        # другой ключ, и повторный импорт создал бы второго сотрудника.
        return str(int(raw))
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    return str(raw).strip()


def _key_component(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip().lower()


def make_key(fields: tuple[str, ...], values: dict[str, Any]) -> str:
    return KEY_SEPARATOR.join(_key_component(values.get(f)) for f in fields)


def resolve_rows(
    target: ImportTarget,
    parsed: ParsedFile,
    mapping: dict[str, str],
    lookups: dict[str, dict[str, str]],
) -> tuple[list[ResolvedRow], dict[str, list[str]]]:
    """Файл → значения полей модели + построчные ошибки + естественный ключ.

    Второй элемент — неизвестные значения справочников, сгруппированные по имени
    справочника (разд. 71.3: «незнакомые значения — предложить создать или
    сопоставить, а не молча пропустить»).
    """

    unknown: dict[str, list[str]] = {}
    resolved: list[ResolvedRow] = []
    seen_keys: dict[str, int] = {}

    for index, source in enumerate(parsed.rows, start=2):  # строка 1 — заголовки
        row = ResolvedRow(row_number=index, raw=dict(source))
        lookup_pending: list[tuple[ImportColumn, str]] = []

        for column in target.columns:
            header = mapping.get(column.field)
            raw = source.get(header) if header else None
            text = _stringify(raw) if raw is not None else ""

            if not text:
                if column.required:
                    row.errors.append(
                        RowError("required", f"{column.title}: value is required", column.field)
                    )
                continue

            if column.lookup:
                lookup_pending.append((column, text))
                if column.also_set_raw:
                    row.values[column.also_set_raw] = text
                continue

            if column.kind == "date":
                value, error = _coerce_date(raw)
            elif column.kind == "int":
                value, error = _coerce_int(raw)
            elif column.kind == "enum":
                value, error = _coerce_enum(raw, column)
            else:
                value, error = text, None
                if column.max_length and len(text) > column.max_length:
                    value, error = (
                        None,
                        f"value is longer than {column.max_length} characters",
                    )

            if error:
                row.errors.append(
                    RowError("invalid_value", f"{column.title}: {error}", column.field)
                )
            elif value is not None:
                row.values[column.field] = value

        # Справочники резолвятся ПОСЛЕ обычных полей: ключ подчинённого справочника
        # (должность внутри организации) опирается на уже разобранную организацию.
        for column, text in lookup_pending:
            scope = ""
            if column.lookup_scope_field:
                scope_value = row.values.get(column.lookup_scope_field)
                if scope_value is None:
                    # Организация не разобралась — про должность сказать нечего;
                    # вторая ошибка на ту же причину только зашумит отчёт.
                    continue
                scope = str(scope_value)
            table = lookups.get(column.lookup, {})
            key = (
                f"{scope}{KEY_SEPARATOR}{normalize_header(text)}"
                if scope
                else normalize_header(text)
            )
            found = table.get(key)
            if found is None:
                row.errors.append(
                    RowError(
                        "unknown_reference",
                        f"{column.title}: {text!r} is not found in the {column.lookup} catalogue",
                        column.field,
                    )
                )
                bucket = unknown.setdefault(column.lookup, [])
                if text not in bucket:
                    bucket.append(text)
                continue
            row.values[column.field] = found

        if row.ok:
            for natural in target.natural_keys:
                if all(row.values.get(f) not in (None, "") for f in natural.fields):
                    row.natural_key = f"{natural.title}{KEY_SEPARATOR}" + make_key(
                        natural.fields, row.values
                    )
                    row.key_title = natural.title
                    break
            if row.natural_key is None:
                variants = " | ".join(k.title for k in target.natural_keys)
                row.errors.append(
                    RowError(
                        "no_natural_key",
                        "Row has no identifying key, so a repeated import would duplicate it. "
                        f"Fill one of: {variants}",
                    )
                )
            elif row.natural_key in seen_keys:
                row.errors.append(
                    RowError(
                        "duplicate_in_file",
                        f"Duplicate of row {seen_keys[row.natural_key]} by {row.key_title}",
                    )
                )
            else:
                seen_keys[row.natural_key] = index

        resolved.append(row)

    return resolved, unknown


def build_plan(
    target: ImportTarget,
    resolved: list[ResolvedRow],
    existing: dict[str, dict[str, Any]],
    mapping: dict[str, str],
    unmapped_headers: list[str],
    unknown_references: dict[str, list[str]],
) -> ImportPlan:
    """Сверка разобранных строк с текущим состоянием → действия."""

    plan = ImportPlan(
        mapping=dict(mapping),
        unmapped_headers=list(unmapped_headers),
        unknown_references={k: list(v) for k, v in unknown_references.items()},
    )

    for row in resolved:
        if not row.ok:
            plan.rows.append(
                PlannedRow(
                    row_number=row.row_number,
                    action="error",
                    natural_key=row.natural_key,
                    errors=list(row.errors),
                )
            )
            continue

        current = existing.get(row.natural_key or "")
        if current is None:
            plan.rows.append(
                PlannedRow(
                    row_number=row.row_number,
                    action="create",
                    natural_key=row.natural_key,
                    values=dict(row.values),
                )
            )
            continue

        # Из сравнения исключаются поля ТОЛЬКО ТОГО ключа, по которому запись
        # нашлась, — по ним она и опознана, «изменением» они быть не могут.
        # Исключать поля ВСЕХ вариантов ключа нельзя: тогда файл с табельными
        # номерами не смог бы исправить опечатку в фамилии, потому что фамилия
        # входит в запасной ключ. Ошибка тем неприятнее, что выглядит как
        # успешный импорт, в котором ничего не поменялось.
        matched_key = next((k for k in target.natural_keys if k.title == row.key_title), None)
        frozen = set(matched_key.fields) if matched_key else set()
        changed = {
            field_name: value
            for field_name, value in row.values.items()
            if field_name not in frozen and current.get(field_name) != value
        }
        if not changed:
            # Повторный импорт того же файла попадает сюда целиком —
            # это и есть идемпотентность из разд. 71.1.
            plan.rows.append(
                PlannedRow(
                    row_number=row.row_number,
                    action="skip",
                    natural_key=row.natural_key,
                    entity_id=current.get("id"),
                )
            )
            continue

        plan.rows.append(
            PlannedRow(
                row_number=row.row_number,
                action="update",
                natural_key=row.natural_key,
                values=changed,
                before={f: current.get(f) for f in changed},
                entity_id=current.get("id"),
            )
        )

    return plan
