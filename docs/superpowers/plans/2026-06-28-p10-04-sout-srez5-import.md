# P10-04 СОУТ срез-5 «Импорт отчёта СОУТ + валидация» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Загрузка файла отчёта СОУТ (Excel/CSV + ФГИС XML) → парсинг в нормализованный формат → валидация → diff против существующей кампании → preview (read) + apply (запись в существующие таблицы), без миграции.

**Architecture:** 3-слойное зеркало среза-4: чистый домен `import_report.py` (датаклассы + парсеры форматов + class-label + validate + diff, без I/O БД) → сервис `sout_import.py` (tenant-scoped загрузка + сборка `ImportPreview`/`ImportResult`, переиспользует `build_class_history_row`) → 2 multipart-эндпоинта в `routes/sout.py` (preview + apply) → тонкий фронт. Apply пишет ТОЛЬКО в существующие `sout_workplace`/`sout_factor`/`sout_class_history` → миграции нет.

**Tech Stack:** Python 3.12 (CI; локально 3.13.7/.venv в КОРНЕ репо), FastAPI, SQLAlchemy async, openpyxl/csv/xml.etree (stdlib); React/Vite/TS, vitest. pytest.

**Спека:** `docs/superpowers/specs/2026-06-28-p10-04-sout-srez5-import-design.md`

**Среда запуска тестов (Win):** summary-строка теряется в PowerShell-буфере — судить по EXIT-коду. Запуск backend: `cd backend && .venv\Scripts\python -m pytest tests/test_X.py -q`. Канон Py3.12 PG CI = финальный гейт.

**Уточнение к спеке:** правило «дубль workplace_code» = **конфликтующий дубль** (один код, но разные класс/должность в разных строках) — повторные строки с одним кодом штатно группируются в один РМ с несколькими факторами; ошибкой считается только конфликт атрибутов.

---

## File Structure

- **Create** `backend/app/domains/sout/import_report.py` — чистый домен: датаклассы `ParsedWorkplace`/`ParsedFactor`/`RowIssues`/`DiffRow`, `parse_class_label`, парсеры `parse_csv`/`parse_xlsx`/`parse_fgis_xml`/`parse_report`, `validate_parsed`, `diff_campaign`, `UnsupportedImportFormat`.
- **Create** `backend/app/services/sout_import.py` — `preview_import`/`apply_import` (БД → схемы), `ImportValidationError`.
- **Modify** `backend/app/schemas/sout.py` — `ImportFactorRow`, `ImportWorkplaceRow`, `ImportPreview`, `ImportResult` (+ импорт `Literal`).
- **Modify** `backend/app/api/routes/sout.py` — эндпоинты `POST /{cid}/import/preview` + `POST /{cid}/import/apply` (+ импорты).
- **Modify** `frontend/src/api/sout.ts` — интерфейсы + `previewImport`/`applyImport`.
- **Modify** `frontend/src/pages/sout/SoutPage.tsx` — секция «Импорт отчёта СОУТ».
- **Create** tests: `backend/tests/test_sout_import_domain.py`, `backend/tests/test_sout_import_service.py`, `backend/tests/test_sout_import_api.py`, `frontend/src/__tests__/SoutImport.test.tsx`.

---

## Task 1: Чистый домен — class-label + датаклассы + validate + diff

**Files:**
- Create: `backend/app/domains/sout/import_report.py`
- Test: `backend/tests/test_sout_import_domain.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_import_domain.py
"""Юниты чистого домена импорта СОУТ (без БД, без async)."""
from app.domains.sout.import_report import (
    DiffRow,
    ParsedFactor,
    ParsedWorkplace,
    UnsupportedImportFormat,
    diff_campaign,
    parse_class_label,
    parse_report,
    validate_parsed,
)


def test_parse_class_label_digits_enum_ru():
    assert parse_class_label("3.1") == ("harmful_3_1", None)
    assert parse_class_label("2") == ("acceptable", None)
    assert parse_class_label("optimal") == ("optimal", None)
    assert parse_class_label("Допустимый") == ("acceptable", None)
    assert parse_class_label("класс 3.2") == ("harmful_3_2", None)
    assert parse_class_label("вредный 3.4") == ("harmful_3_4", None)


def test_parse_class_label_blank_and_garbage():
    assert parse_class_label(None) == (None, None)
    assert parse_class_label("   ") == (None, None)
    assert parse_class_label("абракадабра") == (None, "абракадабра")


def _wp(code="РМ-01", pos="Слесарь", cls="acceptable", factors=None, conflict=False):
    return ParsedWorkplace(
        workplace_code=code, position_name=pos, assessed_class=cls,
        class_unparsed=None, factors=factors or [], conflict=conflict,
    )


def test_validate_blocking_rules():
    rows = [
        _wp(code="", pos="X"),                       # пустой код
        _wp(code="РМ-2", pos=""),                     # пустая должность
        ParsedWorkplace("РМ-3", "X", None, "мусор", []),  # класс не распознан
        _wp(code="РМ-4", conflict=True),             # конфликт атрибутов
    ]
    issues = validate_parsed(rows)
    assert issues[0].errors and issues[1].errors and issues[2].errors and issues[3].errors


def test_validate_warning_class_2_with_harmful_factor():
    wp = _wp(cls="acceptable", factors=[ParsedFactor(None, "Шум", "harmful_3_1", None)])
    issues = validate_parsed([wp])
    assert issues[0].errors == []
    assert any("вредный фактор" in w for w in issues[0].warnings)


def test_validate_warning_unparsed_factor_class():
    wp = _wp(factors=[ParsedFactor(None, "Вибрация", None, "???")])
    issues = validate_parsed([wp])
    assert any("фактор" in w for w in issues[0].warnings)


def test_diff_campaign_classifies():
    parsed = [_wp(code="РМ-1", cls="acceptable"), _wp(code="РМ-2", cls="harmful_3_1"), _wp(code="РМ-3", cls="optimal")]
    existing = [("РМ-1", "acceptable"), ("РМ-2", "optimal"), ("РМ-9", "acceptable")]
    by_code = {d.workplace_code: d for d in diff_campaign(parsed, existing)}
    assert by_code["РМ-1"].change == "unchanged"
    assert by_code["РМ-2"].change == "changed"
    assert by_code["РМ-3"].change == "new"
    assert by_code["РМ-9"].change == "removed"


def test_parse_report_rejects_unknown_extension():
    try:
        parse_report(b"x", "report.pdf")
        assert False, "expected UnsupportedImportFormat"
    except UnsupportedImportFormat:
        pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_domain.py -q`
Expected: FAIL — `ModuleNotFoundError: app.domains.sout.import_report`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domains/sout/import_report.py
"""Чистый домен импорта отчёта СОУТ (без sqlalchemy / без I/O БД).

Три формат-парсера (csv/xlsx/ФГИС xml) сходятся к одному нормализованному
промежуточному формату ParsedWorkplace; валидация и diff — формат-независимы.
RU-метки классов берём из соседнего print_form.py (один контур)."""
from __future__ import annotations

import csv
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from io import BytesIO, StringIO

from app.domains.sout.print_form import HARMFUL_CLASSES


class UnsupportedImportFormat(Exception):
    """Расширение файла не имеет парсера."""


# Прямая карта распознавания класса: нормализованный токен -> значение SoutClass.
_CLASS_ALIASES = {
    "1": "optimal", "optimal": "optimal", "оптимальный": "optimal",
    "2": "acceptable", "acceptable": "acceptable", "допустимый": "acceptable",
    "3.1": "harmful_3_1", "harmful_3_1": "harmful_3_1",
    "3.2": "harmful_3_2", "harmful_3_2": "harmful_3_2",
    "3.3": "harmful_3_3", "harmful_3_3": "harmful_3_3",
    "3.4": "harmful_3_4", "harmful_3_4": "harmful_3_4",
    "4": "dangerous", "dangerous": "dangerous", "опасный": "dangerous",
}


def parse_class_label(raw) -> tuple[str | None, str | None]:
    """(value, unparsed). value = значение SoutClass, либо unparsed = исходная строка."""
    if raw is None:
        return None, None
    token = str(raw).strip().lower()
    if not token:
        return None, None
    for prefix in ("подкласс", "класс", "subclass", "class"):
        if token.startswith(prefix):
            token = token[len(prefix):].strip()
            break
    token = token.replace(",", ".")
    if token in _CLASS_ALIASES:
        return _CLASS_ALIASES[token], None
    parts = token.split()
    if parts and parts[-1] in _CLASS_ALIASES:
        return _CLASS_ALIASES[parts[-1]], None
    return None, str(raw).strip()


@dataclass
class ParsedFactor:
    code: str | None
    name: str
    measured_class: str | None
    class_unparsed: str | None


@dataclass
class ParsedWorkplace:
    workplace_code: str
    position_name: str
    assessed_class: str | None
    class_unparsed: str | None
    factors: list[ParsedFactor] = field(default_factory=list)
    conflict: bool = False  # один код встретился с разными классом/должностью


@dataclass
class RowIssues:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiffRow:
    workplace_code: str
    change: str  # new | changed | unchanged | removed
    parsed_class: str | None
    current_class: str | None


# --- column aliases (RU + EN), нижний регистр ---
_WP_CODE_KEYS = ("workplace_code", "код рм", "код", "номер рм", "рабочее место")
_WP_POS_KEYS = ("position_name", "должность", "профессия", "наименование должности")
_WP_CLASS_KEYS = ("assessed_class", "класс", "итоговый класс", "класс условий труда")
_F_CODE_KEYS = ("factor_code", "код фактора")
_F_NAME_KEYS = ("factor_name", "фактор", "наименование фактора", "вредный фактор")
_F_CLASS_KEYS = ("factor_class", "класс фактора")


def _pick(norm_row: dict, keys) -> object | None:
    for k in keys:
        if k in norm_row and norm_row[k] not in (None, ""):
            return norm_row[k]
    return None


def _rows_to_workplaces(dict_rows) -> list[ParsedWorkplace]:
    order: list[str] = []
    by_code: dict[str, ParsedWorkplace] = {}
    for row in dict_rows:
        norm = {(str(k).strip().lower() if k is not None else ""): v for k, v in row.items()}
        code = str(_pick(norm, _WP_CODE_KEYS) or "").strip()
        pos = str(_pick(norm, _WP_POS_KEYS) or "").strip()
        ac_val, ac_unparsed = parse_class_label(_pick(norm, _WP_CLASS_KEYS))
        if code not in by_code:
            by_code[code] = ParsedWorkplace(
                workplace_code=code, position_name=pos,
                assessed_class=ac_val, class_unparsed=ac_unparsed, factors=[],
            )
            order.append(code)
        else:
            wp = by_code[code]
            # повторная строка с тем же кодом: конфликт, если непустой класс/должность отличаются
            if pos and pos != wp.position_name:
                wp.conflict = True
            if ac_val is not None and wp.assessed_class is not None and ac_val != wp.assessed_class:
                wp.conflict = True
        wp = by_code[code]
        fname = _pick(norm, _F_NAME_KEYS)
        if fname:
            fc_val, fc_unparsed = parse_class_label(_pick(norm, _F_CLASS_KEYS))
            fcode = _pick(norm, _F_CODE_KEYS)
            wp.factors.append(ParsedFactor(
                code=(str(fcode).strip() if fcode else None),
                name=str(fname).strip(), measured_class=fc_val, class_unparsed=fc_unparsed,
            ))
    return [by_code[c] for c in order]


def parse_csv(content: bytes) -> list[ParsedWorkplace]:
    reader = csv.DictReader(StringIO(content.decode("utf-8-sig")))
    rows = [dict(r) for r in reader if any(v not in (None, "") for v in r.values())]
    return _rows_to_workplaces(rows)


def parse_xlsx(content: bytes) -> list[ParsedWorkplace]:
    from openpyxl import load_workbook  # ленивый импорт (тяжёлый), как в documents.py

    wb = load_workbook(BytesIO(content), read_only=True)
    raw = list(wb.active.iter_rows(values_only=True))
    if not raw:
        return []
    headers = [str(c).strip() if c is not None else "" for c in raw[0]]
    rows = []
    for r in raw[1:]:
        entry = {h: v for h, v in zip(headers, r) if h}
        if any(v not in (None, "") for v in entry.values()):
            rows.append(entry)
    return _rows_to_workplaces(rows)


def parse_fgis_xml(content: bytes) -> list[ParsedWorkplace]:
    """Прагматичный субсет ФГИС СОУТ. Схема-допущение:

    <sout><workplace code="РМ-01" position="Слесарь">
        <assessed_class>acceptable</assessed_class>
        <factors><factor code="4.50" name="Шум" class="harmful_3_1"/></factors>
    </workplace></sout>

    TODO: сверить с реальной выгрузкой ФГИС СОУТ (образца в репо нет)."""
    root = ET.fromstring(content)
    out: list[ParsedWorkplace] = []
    for wp_el in root.iter("workplace"):
        code = (wp_el.get("code") or wp_el.findtext("code") or "").strip()
        pos = (wp_el.get("position") or wp_el.findtext("position") or "").strip()
        ac_val, ac_unparsed = parse_class_label(wp_el.findtext("assessed_class"))
        factors = []
        for f_el in wp_el.iter("factor"):
            fname = (f_el.get("name") or f_el.findtext("name") or "").strip()
            if not fname:
                continue
            fc_val, fc_unparsed = parse_class_label(f_el.get("class") or f_el.findtext("class"))
            factors.append(ParsedFactor(
                code=(f_el.get("code") or None), name=fname,
                measured_class=fc_val, class_unparsed=fc_unparsed,
            ))
        out.append(ParsedWorkplace(
            workplace_code=code, position_name=pos,
            assessed_class=ac_val, class_unparsed=ac_unparsed, factors=factors,
        ))
    return out


def parse_report(content: bytes, filename: str) -> list[ParsedWorkplace]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        return parse_csv(content)
    if name.endswith(".xlsx"):
        return parse_xlsx(content)
    if name.endswith(".xml"):
        return parse_fgis_xml(content)
    raise UnsupportedImportFormat(f"неподдерживаемый формат файла: {filename}")


def validate_parsed(workplaces) -> dict[int, RowIssues]:
    issues: dict[int, RowIssues] = {}
    for i, wp in enumerate(workplaces):
        ri = RowIssues()
        if not wp.workplace_code:
            ri.errors.append("пустой код рабочего места")
        if not wp.position_name:
            ri.errors.append("пустая должность")
        if wp.class_unparsed:
            ri.errors.append(f"не распознан класс условий труда: {wp.class_unparsed!r}")
        if wp.conflict:
            ri.errors.append("конфликт атрибутов РМ (один код, разные класс/должность)")
        if wp.assessed_class in ("optimal", "acceptable") and any(
            f.measured_class in HARMFUL_CLASSES for f in wp.factors
        ):
            ri.warnings.append("класс 1-2, но указан вредный фактор (3.1+)")
        for f in wp.factors:
            if f.class_unparsed:
                ri.warnings.append(f"не распознан класс фактора {f.name!r}: {f.class_unparsed!r}")
        issues[i] = ri
    return issues


def diff_campaign(parsed, existing) -> list[DiffRow]:
    """existing: list[(workplace_code, assessed_class_value)]."""
    existing_map = {code: cls for code, cls in existing}
    seen: set[str] = set()
    out: list[DiffRow] = []
    for wp in parsed:
        seen.add(wp.workplace_code)
        if wp.workplace_code not in existing_map:
            change = "new"
        elif existing_map[wp.workplace_code] != wp.assessed_class:
            change = "changed"
        else:
            change = "unchanged"
        out.append(DiffRow(wp.workplace_code, change, wp.assessed_class, existing_map.get(wp.workplace_code)))
    for code, cls in existing:
        if code not in seen:
            out.append(DiffRow(code, "removed", None, cls))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_domain.py -q`
Expected: PASS (8 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/sout/import_report.py backend/tests/test_sout_import_domain.py
git commit -m "feat(sout): import domain — parsers + class-label + validate + diff (срез-5)"
```

---

## Task 2: Парсеры форматов — тесты на csv/xlsx/xml + группировку

**Files:**
- Test: `backend/tests/test_sout_import_domain.py` (дополнить)

- [ ] **Step 1: Write the failing test**

Добавить в конец `backend/tests/test_sout_import_domain.py`:

```python
from io import BytesIO

from app.domains.sout.import_report import parse_csv, parse_fgis_xml, parse_xlsx


def test_parse_csv_groups_factors_by_code():
    csv_text = (
        "workplace_code,position_name,assessed_class,factor_name,factor_class\n"
        "РМ-01,Слесарь,3.1,Шум,3.1\n"
        "РМ-01,Слесарь,3.1,Вибрация,2\n"
        "РМ-02,Сварщик,2,,\n"
    ).encode("utf-8")
    wps = parse_csv(csv_text)
    assert [w.workplace_code for w in wps] == ["РМ-01", "РМ-02"]
    assert wps[0].assessed_class == "harmful_3_1"
    assert [f.name for f in wps[0].factors] == ["Шум", "Вибрация"]
    assert wps[0].factors[0].measured_class == "harmful_3_1"
    assert wps[1].factors == []


def test_parse_csv_detects_conflict_on_repeated_code():
    csv_text = (
        "workplace_code,position_name,assessed_class\n"
        "РМ-01,Слесарь,2\n"
        "РМ-01,Слесарь,3.1\n"  # тот же код, другой класс → конфликт
    ).encode("utf-8")
    wps = parse_csv(csv_text)
    assert wps[0].conflict is True


def test_parse_csv_russian_headers():
    csv_text = (
        "Код РМ,Должность,Класс\n"
        "РМ-05,Оператор,допустимый\n"
    ).encode("utf-8")
    wps = parse_csv(csv_text)
    assert wps[0].workplace_code == "РМ-05"
    assert wps[0].position_name == "Оператор"
    assert wps[0].assessed_class == "acceptable"


def test_parse_xlsx_roundtrip():
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["workplace_code", "position_name", "assessed_class", "factor_name", "factor_class"])
    ws.append(["РМ-01", "Слесарь", "3.1", "Шум", "3.1"])
    buf = BytesIO()
    wb.save(buf)
    wps = parse_xlsx(buf.getvalue())
    assert wps[0].workplace_code == "РМ-01"
    assert wps[0].assessed_class == "harmful_3_1"
    assert wps[0].factors[0].name == "Шум"


def test_parse_fgis_xml_subset():
    xml = (
        "<sout><workplace code='РМ-01' position='Слесарь'>"
        "<assessed_class>acceptable</assessed_class>"
        "<factors><factor code='4.50' name='Шум' class='harmful_3_1'/>"
        "<factor name='Вибрация' class='2'/></factors>"
        "</workplace></sout>"
    ).encode("utf-8")
    wps = parse_fgis_xml(xml)
    assert wps[0].workplace_code == "РМ-01"
    assert wps[0].position_name == "Слесарь"
    assert wps[0].assessed_class == "acceptable"
    assert [f.name for f in wps[0].factors] == ["Шум", "Вибрация"]
    assert wps[0].factors[0].measured_class == "harmful_3_1"
```

- [ ] **Step 2: Run test to verify it fails/passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_domain.py -q`
Expected: PASS (13 passed) — Task 1 уже реализовал парсеры; эти тесты их фиксируют. Если что-то падает (например, конфликт/группировка) — поправить `_rows_to_workplaces`/`parse_*` в `import_report.py` до зелёного.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_sout_import_domain.py
git commit -m "test(sout): pin import parsers (csv/xlsx/fgis-xml + grouping/conflict) срез-5"
```

---

## Task 3: Схемы `ImportPreview` / `ImportResult`

**Files:**
- Modify: `backend/app/schemas/sout.py`

- [ ] **Step 1: Write the failing test**

Создать `backend/tests/test_sout_import_service.py` с первым тестом:

```python
# backend/tests/test_sout_import_service.py
"""Тесты сервиса импорта СОУТ + схем (часть без БД)."""


def test_import_preview_schema_roundtrip():
    from app.schemas.sout import ImportFactorRow, ImportPreview, ImportWorkplaceRow

    row = ImportWorkplaceRow(
        row_index=0, workplace_code="РМ-01", position_name="Слесарь",
        parsed_class="acceptable", current_class=None, change="new",
        factors=[ImportFactorRow(code=None, name="Шум", parsed_class="harmful_3_1", class_unparsed=None)],
        errors=[], warnings=["класс 1-2, но указан вредный фактор (3.1+)"],
    )
    preview = ImportPreview(
        campaign_id="c1", rows=[row], new_count=1, changed_count=0,
        unchanged_count=0, removed_count=0, error_count=0, can_apply=True,
    )
    assert preview.rows[0].change == "new"
    assert preview.can_apply is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_service.py -q`
Expected: FAIL — `ImportError: cannot import name 'ImportPreview'`

- [ ] **Step 3: Write minimal implementation**

В `backend/app/schemas/sout.py` убедиться, что в начале есть `from typing import Literal` (добавить, если нет), и добавить в конец файла:

```python
# --- Import of СОУТ report (срез-5) ---
class ImportFactorRow(BaseSchema):
    code: str | None
    name: str
    parsed_class: str | None
    class_unparsed: str | None


class ImportWorkplaceRow(BaseSchema):
    row_index: int
    workplace_code: str
    position_name: str
    parsed_class: str | None
    current_class: str | None
    change: Literal["new", "changed", "unchanged", "removed"]
    factors: list[ImportFactorRow]
    errors: list[str]
    warnings: list[str]


class ImportPreview(BaseSchema):
    campaign_id: str
    rows: list[ImportWorkplaceRow]
    new_count: int
    changed_count: int
    unchanged_count: int
    removed_count: int
    error_count: int
    can_apply: bool


class ImportResult(BaseSchema):
    campaign_id: str
    created: int
    updated: int
    skipped: int
    removed_detected: int
    errors: list[str]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_service.py -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/sout.py backend/tests/test_sout_import_service.py
git commit -m "feat(sout): import preview/result schemas (срез-5)"
```

---

## Task 4: Сервис `sout_import.py` — preview + apply

**Files:**
- Create: `backend/app/services/sout_import.py`
- Test: `backend/tests/test_sout_import_service.py` (дополнить — DB-тесты)

- [ ] **Step 1: Write the failing test**

Добавить в `backend/tests/test_sout_import_service.py`:

```python
import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import TenantBase
import app.models.sout  # noqa: F401  — регистрирует sout-таблицы в metadata
from app.models.sout import SoutCampaign, SoutClass, SoutClassHistory, SoutFactor, SoutWorkplace
from app.services.sout_import import ImportValidationError, apply_import, preview_import


# Локальная in-memory SQLite сессия (паттерн test_dq_medical.py — общего conftest нет).
@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


class _Tenant:
    def __init__(self, tid="tenant-1"):
        self.id = tid


def _csv(rows: str) -> bytes:
    header = "workplace_code,position_name,assessed_class,factor_name,factor_class\n"
    return (header + rows).encode("utf-8")


@pytest.fixture()
async def campaign(db_session):
    t = _Tenant()
    c = SoutCampaign(tenant_id=t.id, name="СОУТ 2026")
    db_session.add(c)
    await db_session.flush()
    # одно существующее РМ для diff
    db_session.add(SoutWorkplace(
        tenant_id=t.id, campaign_id=c.id, workplace_code="РМ-01",
        position_name="Слесарь", assessed_class=SoutClass.ACCEPTABLE,
    ))
    await db_session.flush()
    return t, c


@pytest.mark.asyncio
async def test_preview_classifies_new_changed_unchanged(db_session, campaign):
    t, c = campaign
    content = _csv(
        "РМ-01,Слесарь,3.1,,\n"     # changed (было acceptable)
        "РМ-02,Сварщик,2,,\n"        # new
    )
    preview = await preview_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    by_code = {r.workplace_code: r for r in preview.rows}
    assert by_code["РМ-01"].change == "changed"
    assert by_code["РМ-02"].change == "new"
    assert preview.new_count == 1 and preview.changed_count == 1
    assert preview.can_apply is True


@pytest.mark.asyncio
async def test_preview_missing_campaign_returns_none(db_session):
    t = _Tenant()
    out = await preview_import(db_session, tenant=t, campaign_id="nope", content=_csv("РМ-9,X,2,,\n"), filename="r.csv")
    assert out is None


@pytest.mark.asyncio
async def test_apply_creates_updates_and_writes_history(db_session, campaign):
    t, c = campaign
    content = _csv(
        "РМ-01,Слесарь,3.1,,\n"          # changed → history old=acceptable new=3.1
        "РМ-02,Сварщик,2,Шум,3.1\n"      # new + factor
    )
    result = await apply_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    assert result.created == 1 and result.updated == 1
    await db_session.flush()
    wps = (await db_session.execute(
        select(SoutWorkplace).where(SoutWorkplace.campaign_id == c.id)
    )).scalars().all()
    assert {w.workplace_code for w in wps} == {"РМ-01", "РМ-02"}
    rm01 = next(w for w in wps if w.workplace_code == "РМ-01")
    assert rm01.assessed_class == SoutClass.HARMFUL_3_1
    factors = (await db_session.execute(select(SoutFactor))).scalars().all()
    assert any(f.name == "Шум" and f.measured_class == SoutClass.HARMFUL_3_1 for f in factors)
    hist = (await db_session.execute(select(SoutClassHistory))).scalars().all()
    assert any(h.new_class == SoutClass.HARMFUL_3_1 for h in hist)


@pytest.mark.asyncio
async def test_apply_all_or_nothing_on_blocking_error(db_session, campaign):
    t, c = campaign
    content = _csv("РМ-03,,2,,\n")  # пустая должность → блокирующая ошибка
    with pytest.raises(ImportValidationError):
        await apply_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    # ничего не создано
    wps = (await db_session.execute(
        select(SoutWorkplace).where(SoutWorkplace.workplace_code == "РМ-03")
    )).scalars().all()
    assert wps == []


@pytest.mark.asyncio
async def test_apply_idempotent_second_run_is_noop(db_session, campaign):
    t, c = campaign
    content = _csv("РМ-01,Слесарь,2,,\n")  # совпадает с существующим → unchanged
    result = await apply_import(db_session, tenant=t, campaign_id=c.id, content=content, filename="r.csv")
    assert result.created == 0 and result.updated == 0 and result.skipped == 1
```

> **Note:** общего conftest-fixture для async-сессии в репо нет — DB-тесты определяют локальную in-memory SQLite сессию (паттерн `test_dq_medical.py`, воспроизведён выше). `import app.models.sout` обязателен, чтобы sout-таблицы зарегистрировались в `TenantBase.metadata` до `create_all`. FK на person/position/risk_hazards в SQLite не мешают `create_all` (FK к отсутствующей таблице не ломает DDL).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_service.py -q`
Expected: FAIL — `ModuleNotFoundError: app.services.sout_import`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/services/sout_import.py
"""Импорт отчёта СОУТ: файл → diff → preview (read) / apply (запись).

Зеркало services/sout_declaration.py. Пишет ТОЛЬКО в существующие
sout_workplace/sout_factor/sout_class_history (миграции нет). apply повторно
парсит файл (не доверяет клиентскому preview) → идемпотентность по workplace_code."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.sout import import_report as imp
from app.domains.sout.service import build_class_history_row
from app.models.sout import SoutCampaign, SoutClass, SoutFactor, SoutWorkplace
from app.models.tenanting import Tenant
from app.schemas.sout import (
    ImportFactorRow,
    ImportPreview,
    ImportResult,
    ImportWorkplaceRow,
)


class ImportValidationError(Exception):
    """Блокирующие ошибки валидации при apply (→422, без записей)."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def _raw(value):
    return getattr(value, "value", value)


def _to_class(value: str | None) -> SoutClass | None:
    return SoutClass(value) if value else None


async def _load_campaign(session: AsyncSession, tenant: Tenant, cid: str) -> SoutCampaign | None:
    return (
        await session.execute(
            select(SoutCampaign).where(
                SoutCampaign.id == cid,
                SoutCampaign.tenant_id == tenant.id,
                SoutCampaign.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _load_existing(session: AsyncSession, tenant: Tenant, cid: str):
    rows = list(
        (
            await session.execute(
                select(SoutWorkplace).where(
                    SoutWorkplace.campaign_id == cid,
                    SoutWorkplace.tenant_id == tenant.id,
                    SoutWorkplace.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    )
    pairs = [(w.workplace_code, _raw(w.assessed_class)) for w in rows]
    by_code = {w.workplace_code: w for w in rows}
    return pairs, by_code


def _assemble_preview(cid: str, parsed, existing_pairs) -> ImportPreview:
    issues = imp.validate_parsed(parsed)
    diff = imp.diff_campaign(parsed, existing_pairs)
    diff_by_code = {d.workplace_code: d for d in diff}
    rows: list[ImportWorkplaceRow] = []
    error_count = 0
    for i, wp in enumerate(parsed):
        ri = issues.get(i, imp.RowIssues())
        if ri.errors:
            error_count += 1
        d = diff_by_code.get(wp.workplace_code)
        rows.append(
            ImportWorkplaceRow(
                row_index=i,
                workplace_code=wp.workplace_code,
                position_name=wp.position_name,
                parsed_class=wp.assessed_class,
                current_class=(d.current_class if d else None),
                change=(d.change if d else "new"),
                factors=[
                    ImportFactorRow(
                        code=f.code, name=f.name,
                        parsed_class=f.measured_class, class_unparsed=f.class_unparsed,
                    )
                    for f in wp.factors
                ],
                errors=ri.errors,
                warnings=ri.warnings,
            )
        )
    for d in diff:
        if d.change == "removed":
            rows.append(
                ImportWorkplaceRow(
                    row_index=-1, workplace_code=d.workplace_code, position_name="",
                    parsed_class=None, current_class=d.current_class, change="removed",
                    factors=[], errors=[], warnings=[],
                )
            )
    counts = {"new": 0, "changed": 0, "unchanged": 0, "removed": 0}
    for d in diff:
        counts[d.change] += 1
    return ImportPreview(
        campaign_id=cid,
        rows=rows,
        new_count=counts["new"],
        changed_count=counts["changed"],
        unchanged_count=counts["unchanged"],
        removed_count=counts["removed"],
        error_count=error_count,
        can_apply=error_count == 0,
    )


async def preview_import(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, content: bytes, filename: str
) -> ImportPreview | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    parsed = imp.parse_report(content, filename)
    existing_pairs, _ = await _load_existing(session, tenant, campaign_id)
    return _assemble_preview(campaign_id, parsed, existing_pairs)


async def apply_import(
    session: AsyncSession, *, tenant: Tenant, campaign_id: str, content: bytes, filename: str
) -> ImportResult | None:
    campaign = await _load_campaign(session, tenant, campaign_id)
    if campaign is None:
        return None
    parsed = imp.parse_report(content, filename)
    issues = imp.validate_parsed(parsed)
    blocking = [f"строка {i + 1}: {e}" for i, ri in issues.items() for e in ri.errors]
    if blocking:
        raise ImportValidationError(blocking)
    existing_pairs, by_code = await _load_existing(session, tenant, campaign_id)
    diff_by_code = {d.workplace_code: d for d in imp.diff_campaign(parsed, existing_pairs)}
    created = updated = skipped = 0
    for wp in parsed:
        change = diff_by_code[wp.workplace_code].change
        if change == "new":
            row = SoutWorkplace(
                tenant_id=tenant.id, campaign_id=campaign_id,
                workplace_code=wp.workplace_code, position_name=wp.position_name,
                assessed_class=_to_class(wp.assessed_class),
            )
            session.add(row)
            await session.flush()
            for f in wp.factors:
                session.add(SoutFactor(
                    tenant_id=tenant.id, workplace_id=row.id,
                    code=f.code, name=f.name, measured_class=_to_class(f.measured_class),
                ))
            hist = build_class_history_row(
                tenant_id=tenant.id, workplace_id=row.id,
                old_class=None, new_class=_to_class(wp.assessed_class),
            )
            if hist is not None:
                session.add(hist)
            created += 1
        elif change == "changed":
            existing = by_code[wp.workplace_code]
            old = existing.assessed_class
            new = _to_class(wp.assessed_class)
            existing.assessed_class = new
            hist = build_class_history_row(
                tenant_id=tenant.id, workplace_id=existing.id, old_class=old, new_class=new,
            )
            if hist is not None:
                session.add(hist)
            updated += 1
        else:
            skipped += 1
    removed_detected = sum(1 for d in diff_by_code.values() if d.change == "removed")
    await session.flush()
    return ImportResult(
        campaign_id=campaign_id, created=created, updated=updated,
        skipped=skipped, removed_detected=removed_detected, errors=[],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_service.py -q`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sout_import.py backend/tests/test_sout_import_service.py
git commit -m "feat(sout): import preview + apply service (срез-5)"
```

---

## Task 5: Эндпоинты preview + apply

**Files:**
- Modify: `backend/app/api/routes/sout.py`
- Test: `backend/tests/test_sout_import_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_sout_import_api.py
"""API-контракт импорта СОУТ (monkeypatch, как test_sout_print_api.py)."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import app.api.routes.sout as routes
from app.domains.sout.import_report import UnsupportedImportFormat
from app.schemas.sout import ImportPreview, ImportResult
from app.services.sout_import import ImportValidationError


def _tenant():
    return SimpleNamespace(id="tenant-1", is_active=True, slug="t1", name="ООО Ромашка")


def _file(name="r.csv"):
    return SimpleNamespace(filename=name, read=AsyncMock(return_value=b"x"))


@pytest.mark.asyncio
async def test_preview_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_import", AsyncMock(return_value=ImportPreview(
        campaign_id="c1", rows=[], new_count=0, changed_count=0,
        unchanged_count=0, removed_count=0, error_count=0, can_apply=True,
    )))
    out = await routes.import_preview(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert out.campaign_id == "c1"


@pytest.mark.asyncio
async def test_preview_404_when_campaign_missing(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_import", AsyncMock(return_value=None))
    with pytest.raises(Exception) as exc:
        await routes.import_preview(cid="nope", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_preview_422_on_unsupported_format(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "preview_import", AsyncMock(side_effect=UnsupportedImportFormat("pdf")))
    with pytest.raises(Exception) as exc:
        await routes.import_preview(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file("r.pdf"))
    assert getattr(exc.value, "status_code", None) == 422


@pytest.mark.asyncio
async def test_apply_ok(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_campaign", AsyncMock(return_value=SimpleNamespace(id="c1", status="planned")))
    monkeypatch.setattr(routes, "ensure_campaign_open", lambda s: None)
    monkeypatch.setattr(routes, "apply_import", AsyncMock(return_value=ImportResult(
        campaign_id="c1", created=2, updated=1, skipped=0, removed_detected=0, errors=[],
    )))
    out = await routes.import_apply(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert out.created == 2 and out.updated == 1


@pytest.mark.asyncio
async def test_apply_422_on_validation_error(monkeypatch):
    monkeypatch.setattr(routes, "_require_sout_enabled", AsyncMock())
    monkeypatch.setattr(routes, "_get_campaign", AsyncMock(return_value=SimpleNamespace(id="c1", status="planned")))
    monkeypatch.setattr(routes, "ensure_campaign_open", lambda s: None)
    monkeypatch.setattr(routes, "apply_import", AsyncMock(side_effect=ImportValidationError(["строка 1: пустая должность"])))
    with pytest.raises(Exception) as exc:
        await routes.import_apply(cid="c1", tenant=_tenant(), session=AsyncMock(), access=None, file=_file())
    assert getattr(exc.value, "status_code", None) == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_api.py -q`
Expected: FAIL — `AttributeError: module 'app.api.routes.sout' has no attribute 'import_preview'`

- [ ] **Step 3: Write minimal implementation**

В `backend/app/api/routes/sout.py`:

(a) Расширить импорт fastapi (строка 7) — добавить `File`, `UploadFile`:

```python
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
```

(b) Добавить импорты сервиса/домена/схем рядом с остальными (после блока `from app.services.sout_declaration import ...`):

```python
from app.services.sout_import import (
    ImportValidationError,
    apply_import,
    preview_import,
)
from app.domains.sout.import_report import UnsupportedImportFormat
```

(c) В блок `from app.schemas.sout import (...)` добавить:

```python
    ImportPreview,
    ImportResult,
```

(d) Добавить в конец файла (после `print_declaration`):

```python
def _unsupported_format(exc: UnsupportedImportFormat) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="SOUT_IMPORT_FORMAT", message=str(exc), error_type="sout"
        ),
    )


def _import_invalid(exc: ImportValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="SOUT_IMPORT_INVALID", message="; ".join(exc.errors), error_type="sout"
        ),
    )


@router.post("/{cid}/import/preview", response_model=ImportPreview)
async def import_preview(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    file: Annotated[UploadFile, File()],
) -> ImportPreview:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    content = await file.read()
    try:
        outcome = await preview_import(
            session, tenant=tenant, campaign_id=cid, content=content, filename=file.filename or ""
        )
    except UnsupportedImportFormat as exc:
        raise _unsupported_format(exc)
    if outcome is None:
        raise _not_found("Campaign")
    return outcome


@router.post("/{cid}/import/apply", response_model=ImportResult)
async def import_apply(
    cid: str,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    file: Annotated[UploadFile, File()],
) -> ImportResult:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _require_sout_enabled(session, tenant)
    campaign = await _get_campaign(session, tenant, cid)
    try:
        ensure_campaign_open(campaign.status)
    except CampaignTransitionError as exc:
        raise _conflict(exc)
    content = await file.read()
    try:
        result = await apply_import(
            session, tenant=tenant, campaign_id=cid, content=content, filename=file.filename or ""
        )
    except UnsupportedImportFormat as exc:
        raise _unsupported_format(exc)
    except ImportValidationError as exc:
        raise _import_invalid(exc)
    if result is None:
        raise _not_found("Campaign")
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_api.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: Run the full СОУТ cohort to confirm no regression**

Run: `cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_domain.py tests/test_sout_import_service.py tests/test_sout_import_api.py tests/test_sout_api.py tests/test_sout_service.py tests/test_sout_declaration_api.py tests/test_sout_print_api.py -q`
Expected: PASS (EXIT 0)

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/sout.py backend/tests/test_sout_import_api.py
git commit -m "feat(sout): import preview + apply endpoints (срез-5)"
```

---

## Task 6: Фронт — API + секция «Импорт отчёта СОУТ»

**Files:**
- Modify: `frontend/src/api/sout.ts`
- Modify: `frontend/src/pages/sout/SoutPage.tsx`
- Test: `frontend/src/__tests__/SoutImport.test.tsx`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/__tests__/SoutImport.test.tsx
import { beforeEach, describe, expect, it, vi } from "vitest";

import { soutApi } from "@/api/sout";

vi.mock("@/api/client", () => ({
  apiClient: { post: vi.fn() },
}));

describe("soutApi import methods", () => {
  beforeEach(() => { vi.restoreAllMocks(); });

  it("previewImport posts FormData to the preview endpoint", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { campaign_id: "c1", rows: [], new_count: 0, changed_count: 0, unchanged_count: 0, removed_count: 0, error_count: 0, can_apply: true },
    });
    const file = new File(["x"], "r.csv", { type: "text/csv" });

    const out = await soutApi.previewImport("c1", file);

    expect(apiClient.post).toHaveBeenCalledWith(
      "/sout/c1/import/preview",
      expect.any(FormData),
    );
    expect(out.campaign_id).toBe("c1");
  });

  it("applyImport posts FormData to the apply endpoint", async () => {
    const { apiClient } = await import("@/api/client");
    (apiClient.post as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { campaign_id: "c1", created: 1, updated: 0, skipped: 0, removed_detected: 0, errors: [] },
    });
    const file = new File(["x"], "r.csv", { type: "text/csv" });

    const out = await soutApi.applyImport("c1", file);

    expect(apiClient.post).toHaveBeenCalledWith(
      "/sout/c1/import/apply",
      expect.any(FormData),
    );
    expect(out.created).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/__tests__/SoutImport.test.tsx`
Expected: FAIL — `soutApi.previewImport is not a function`

- [ ] **Step 3: Write minimal implementation (api)**

В `frontend/src/api/sout.ts` добавить интерфейсы после `SoutDeclarationPreview` (перед `// ── API ──`):

```typescript
export interface SoutImportFactorRow {
  code: string | null;
  name: string;
  parsed_class: string | null;
  class_unparsed: string | null;
}

export interface SoutImportWorkplaceRow {
  row_index: number;
  workplace_code: string;
  position_name: string;
  parsed_class: string | null;
  current_class: string | null;
  change: "new" | "changed" | "unchanged" | "removed";
  factors: SoutImportFactorRow[];
  errors: string[];
  warnings: string[];
}

export interface SoutImportPreview {
  campaign_id: string;
  rows: SoutImportWorkplaceRow[];
  new_count: number;
  changed_count: number;
  unchanged_count: number;
  removed_count: number;
  error_count: number;
  can_apply: boolean;
}

export interface SoutImportResult {
  campaign_id: string;
  created: number;
  updated: number;
  skipped: number;
  removed_detected: number;
  errors: string[];
}
```

Добавить методы внутри `soutApi` (после `downloadDeclaration`):

```typescript
  async previewImport(campaignId: string, file: File): Promise<SoutImportPreview> {
    const form = new FormData();
    form.append("file", file);
    return (await apiClient.post<SoutImportPreview>(`${base}/${campaignId}/import/preview`, form)).data;
  },

  async applyImport(campaignId: string, file: File): Promise<SoutImportResult> {
    const form = new FormData();
    form.append("file", file);
    return (await apiClient.post<SoutImportResult>(`${base}/${campaignId}/import/apply`, form)).data;
  },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/__tests__/SoutImport.test.tsx`
Expected: PASS (2 passed)

- [ ] **Step 5: Wire the UI section into SoutPage**

В `frontend/src/pages/sout/SoutPage.tsx`:

(a) Расширить существующий импорт `@/api/sout` типами (добавить к уже импортируемым):

```tsx
  type SoutImportPreview,
  type SoutImportResult,
```

(b) Внутри панели кампании (в том же контейнере, где кнопки «Сводная»/«Декларация» в `ReportPanel`) добавить локальное состояние и хендлеры. Если `ReportPanel` принимает `campaign`, добавить:

```tsx
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<SoutImportPreview | null>(null);

  const handleImportPreview = async () => {
    if (!importFile) return;
    try {
      setImportPreview(await soutApi.previewImport(campaign.id, importFile));
    } catch {
      toast.error("Не удалось разобрать файл (проверьте формат: CSV/XLSX/XML)");
      setImportPreview(null);
    }
  };

  const handleImportApply = async () => {
    if (!importFile) return;
    try {
      const res: SoutImportResult = await soutApi.applyImport(campaign.id, importFile);
      toast.success(`Импорт применён: создано ${res.created}, обновлено ${res.updated}, пропущено ${res.skipped}`);
      setImportPreview(null);
      setImportFile(null);
    } catch (e: unknown) {
      const status = (e as { response?: { status?: number } })?.response?.status;
      toast.error(status === 409 ? "Кампания закрыта для импорта" : "Исправьте ошибки в файле и повторите");
    }
  };
```

(c) Добавить разметку секции внутри `<CardContent>` `ReportPanel` (после блока декларации):

```tsx
        <div className="rounded-md border border-border p-3 text-sm" data-testid="sout-import">
          <p className="font-medium">Импорт отчёта СОУТ</p>
          <p className="text-muted-foreground">Поддерживаются CSV, XLSX, ФГИС XML.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input
              type="file"
              accept=".csv,.xlsx,.xml"
              onChange={(e) => { setImportFile(e.target.files?.[0] ?? null); setImportPreview(null); }}
            />
            <Button type="button" size="sm" variant="outline" disabled={!importFile}
              onClick={() => void handleImportPreview()}>
              Проверить
            </Button>
            <Button type="button" size="sm"
              disabled={!importPreview || !importPreview.can_apply}
              onClick={() => void handleImportApply()}>
              Применить
            </Button>
          </div>
          {importPreview !== null ? (
            <div className="mt-2">
              <p className="text-muted-foreground">
                Новых: {importPreview.new_count} · изменённых: {importPreview.changed_count} ·
                без изменений: {importPreview.unchanged_count} · отсутствуют в файле: {importPreview.removed_count} ·
                ошибок: {importPreview.error_count}
              </p>
              <ul className="mt-1 list-disc pl-5 text-xs">
                {importPreview.rows.map((r) => (
                  <li key={`${r.row_index}-${r.workplace_code}`}>
                    [{r.change}] {r.workplace_code} {r.position_name}
                    {r.errors.length > 0 ? ` — ОШИБКИ: ${r.errors.join("; ")}` : ""}
                    {r.warnings.length > 0 ? ` — предупр.: ${r.warnings.join("; ")}` : ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
```

> Если в файле уже есть импорты `useState`, `Button`, `toast`, `soutApi` — не дублировать; добавить только недостающее. Сверить фактические имена `ReportPanel`/`campaign`/`CardContent` с текущим файлом (срез-4 их уже использует).

- [ ] **Step 6: Verify frontend gates**

Run: `cd frontend && npx vitest run src/__tests__/SoutImport.test.tsx && npx tsc --noEmit && npx eslint src/api/sout.ts src/pages/sout/SoutPage.tsx --max-warnings=0`
Expected: vitest PASS, tsc clean, eslint 0 errors (допустим 1 pre-existing exhaustive-deps на report-`load` effect, как в срезе-4).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/sout.ts frontend/src/pages/sout/SoutPage.tsx frontend/src/__tests__/SoutImport.test.tsx
git commit -m "feat(sout): import UI section + api methods (срез-5)"
```

---

## Task 7: Верификация + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новый handoff-блок сверху)

- [ ] **Step 1: Backend cohort + migration-absence proof**

Run:
```
cd backend && .venv\Scripts\python -m pytest tests/test_sout_import_domain.py tests/test_sout_import_service.py tests/test_sout_import_api.py tests/test_sout_declaration.py tests/test_sout_declaration_service.py tests/test_sout_declaration_api.py tests/test_sout_print_api.py tests/test_sout_api.py tests/test_sout_service.py tests/test_sout_models.py tests/test_sout_schemas.py -q
```
Expected: EXIT 0.

Run (migration dividend proof — must be empty):
```
git diff --name-only origin/main...HEAD -- backend/app/migrations/versions/
```
Expected: пусто (ни одного файла).

- [ ] **Step 2: Frontend build**

Run: `cd frontend && npm run build`
Expected: EXIT 0.

- [ ] **Step 3: Write handoff block**

Prepend a `## Last Agent Handoff (2026-06-28, СОУТ срез-5 импорт отчёта + валидация ...)` section to `AI_IMPLEMENTATION_REPORT.md` summarizing: нормализованный промежуточный формат (3 парсера → ParsedWorkplace), no-migration dividend (proven empty diff), diff-by-workplace_code, all-or-nothing apply, removed=report-only, idempotency, ФГИС XML = pragmatic subset (TODO сверить с реальным файлом), test counts, deferred items (§7 спеки), branch `feat/sout-srez5-import-p10-04`, merge=user's call.

- [ ] **Step 4: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs: handoff for СОУТ срез-5 импорт отчёта + валидация"
```

---

## Self-Review (выполнено при написании плана)

- **Spec coverage:** оба формата (T1 csv/xml + T2 xlsx-тест), diff против кампании (T1 `diff_campaign`, T4 сервис), preview+apply два эндпоинта (T5), валидация всех правил (T1 + T4 all-or-nothing), фронт api+UI (T6), верификация+handoff (T7). Отложенное (§7 спеки) — не реализуется, документировано.
- **No migration:** доказывается T7.1 (`git diff` по migrations/versions пуст); apply пишет в существующие 3 таблицы.
- **Type consistency:** `ParsedWorkplace`/`ParsedFactor`/`DiffRow`/`RowIssues` (домен) ↔ `ImportWorkplaceRow`/`ImportFactorRow`/`ImportPreview`/`ImportResult` (схемы); `change` — общий `Literal[new,changed,unchanged,removed]` в домене (строки) и схеме; `parse_class_label`→`(value, unparsed)` единообразно; `_to_class` коэрсит str→SoutClass перед записью в enum-колонку (анти-грабли: домен оперирует строками-значениями, ORM — enum); `preview_import`/`apply_import`/`parse_report`/`validate_parsed`/`diff_campaign` — имена согласованы между T1/T4/T5 и тестами.
- **Анти-грабли:** класс-2-но-фактор-3.1 → warning и в `validate_parsed` (T1), и в сервис-тесте; конфликтующий дубль кода (а не любой повтор) → blocking; apply «всё-или-ничего» (тест T4); `removed` не удаляет; повторный apply идемпотентен (тест T4); XML factor class из атрибута `class=` (схема-допущение задокументирована).
```
