# Тираж наряда-допуска на ОЗП (902н) + слой профилей видов работ — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить второй полноценный вид наряда-допуска — работа в ограниченных и замкнутых пространствах (ОЗП, Приказ Минтруда № 902н) — и вынуть обобщающий слой «профилей вида работ», чтобы следующие виды добавлялись дёшево.

**Architecture:** Новый чистый модуль `profiles.py` — полиморфный шов: на каждый `work_type` хранит приказ (`legal_reference`), вид структурной секции, валидацию `type_specific`-payload и сборку печатной секции. `print_form.py` генерализуется до тупого рендерера (получает `legal_reference` + generic `StructuredSection`). Высота не трогается (держит колонку `safety_systems`); новые виды текут через новую колонку `type_specific: JSON`.

**Tech Stack:** Python 3.12 (локально 3.13.7/.venv), FastAPI, SQLAlchemy async, Alembic, Pydantic v2, pytest; React/Vite, zod, react-hook-form, vitest.

**Среда/прогон:** Win + `.venv\Scripts\python.exe -m pytest`; сигнал успеха — EXIT-код (итоговая `N passed`-строка теряется блочной буферизацией — см. [[py313_win_pytest_invocation]]). Канон Py3.12.12 CI выключен ([[ci_disabled_actions_off]]) — финальный гейт. Ветка `feat/work-permit-types-confined-space` стопкой поверх `feat/work-permits-782n-print` (Ф4).

**Контракт `type_specific` (ОЗП):**
```jsonc
{
  "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20", "measured_at": "2026-06-21 08:00"}],
  "ventilation": "forced"
}
```
`parameter ∈ {oxygen, flammable, harmful}`, `ventilation ∈ {natural, forced, none, not_required}`.

---

## File Structure

**Создаются:**
- `backend/app/domains/work_permits/profiles.py` — реестр профилей видов работ (чистый).
- `backend/app/migrations/versions/20260621_wp06_work_permit_type_specific.py` — миграция (колонка `type_specific`).
- `tests/test_work_permit_profiles.py` — unit профилей.
- `tests/test_work_permit_type_specific_migration.py` — guard миграции wp06.
- `backend/tests/test_work_permit_confined_schemas.py` — валидация схем `type_specific`.

**Модифицируются:**
- `backend/app/domains/work_permits/print_form.py` — `legal_reference` + `StructuredSection`/`StructuredTable`, generic-рендер.
- `tests/test_work_permit_print_form.py` — обновить под новый `WorkPermitPrintData`.
- `backend/app/models/work_permit.py` — колонка `type_specific`.
- `backend/app/schemas/work_permit.py` — поле `type_specific` + валидация create.
- `backend/app/domains/work_permits/service.py` — `type_specific` в create/update.
- `backend/app/services/work_permit_print.py` — `legal_reference` + `structured_section` через профили.
- `tests/test_work_permit_print_service.py` — добавить ОЗП-кейс.
- `backend/app/api/routes/work_permits.py` — create/update/read проброс + 422-валидация update.
- `frontend/src/lib/workPermitVocab.ts` — словари приказов/газа/вентиляции.
- `frontend/src/types/forms/workPermits.ts`, `frontend/src/types/dto/workPermits.ts` — `type_specific`.
- `frontend/src/features/work-permits/WorkPermitFormDialog.tsx` — условная секция по виду.
- `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` — показ ОЗП-секции.
- `backend/app/services/demo_bootstrap.py` — demo-seed ОЗП-наряда.

---

## Task 1: Генерализация `print_form.py` (legal_reference + StructuredSection)

Чистый рендерер: убираем хардкод «№ 782н», заменяем высото-специфичную строку `safety_systems` на generic-секцию.

**Files:**
- Modify: `backend/app/domains/work_permits/print_form.py`
- Test: `tests/test_work_permit_print_form.py` (переписать `_sample`/ассерты)

- [ ] **Step 1: Обновить тест под новый контракт `WorkPermitPrintData`**

Заменить в `tests/test_work_permit_print_form.py` импорт и `_sample()`/тесты на:

```python
from app.domains.work_permits.print_form import (
    SignatureLine, StructuredSection, StructuredTable, WorkPermitPrintData,
    build_work_permit_docx,
)

# ... _all_text без изменений ...

def _sample() -> WorkPermitPrintData:
    return WorkPermitPrintData(
        number="НД-7", work_type_label="Работа на высоте",
        legal_reference="Приказ Минтруда России от 16.11.2020 № 782н",
        status_label="Выдан", org_header="ООО Ромашка", subdivision="Цех №1",
        planned_start="2026-06-20 08:00", planned_end="2026-06-20 18:00",
        zone_text="фасад корпуса А", content_text="монтаж", conditions_text="ясно",
        equipment_text="люлька", hazards_text="высота 12 м",
        structured_section=StructuredSection(
            title="Системы обеспечения безопасности (782н)",
            kv=[("Системы", "Удерживающие, Страховочные")], table=None),
        measures_before="ограждение", measures_during="наблюдение",
        special_conditions="—", ppe_text="каска, строп",
        members=[("Производитель работ", "Иванов И.И."), ("Допускающий", "Петров П.П.")],
        briefing={"conducted_by_fio": "Иванов И.И.", "conducted_at": "2026-06-20 07:45", "topics": "ТБ на высоте"},
        daily_admissions=[{"date": "2026-06-20", "start": "08:00", "end": "18:00", "admitted_by_fio": "Петров П.П."}],
        extensions=[{"old_end": "2026-06-20 18:00", "new_end": "2026-06-21 18:00", "at": "2026-06-20 17:30"}],
        completion={"text": "работы окончены, место сдано", "recorded_at": "2026-06-21 17:00"},
        closed_at="2026-06-21 17:05",
        signatures=[
            SignatureLine(group="permit", role_label="Производитель работ", fio="Иванов И.И.",
                          status_label="Подписано", signed_at="2026-06-20 08:05", mode="attested",
                          hash_short="a1b2c3d4e5f6a7b8"),
            SignatureLine(group="closing", role_label="Сдал", fio="Иванов И.И.",
                          status_label="Подписано", signed_at="2026-06-21 17:00", mode="attested",
                          hash_short="ffeeddccbbaa9988"),
        ],
    )


def test_build_docx_contains_core_fields():
    text = _all_text(build_work_permit_docx(_sample()))
    assert "НД-7" in text
    assert "Иванов И.И." in text
    assert "№ 782н" in text                  # приказ в шапке (не хардкод)
    assert "Удерживающие, Страховочные" in text  # структурная секция (kv)
    assert "работы окончены, место сдано" in text
    assert "a1b2c3d4e5f6a7b8" in text
    assert "Сдал" in text


def test_build_docx_renders_structured_table():
    data = _sample()
    data.structured_section = StructuredSection(
        title="Анализ воздушной среды (902н)",
        kv=[("Вентиляция", "Принудительная")],
        table=StructuredTable(headers=["Параметр", "Значение"], rows=[["Кислород", "20.9"]]),
    )
    text = _all_text(build_work_permit_docx(data))
    assert "Анализ воздушной среды (902н)" in text
    assert "Вентиляция" in text and "Принудительная" in text
    assert "Кислород" in text and "20.9" in text


def test_build_docx_empty_sections_do_not_crash():
    data = WorkPermitPrintData(
        number="НД-8", work_type_label="Работа на высоте",
        legal_reference="Приказ Минтруда России от 16.11.2020 № 782н",
        status_label="Черновик", org_header="ООО Ромашка", subdivision=None,
        planned_start=None, planned_end=None, zone_text="зона", content_text=None,
        conditions_text=None, equipment_text=None, hazards_text=None,
        structured_section=None, measures_before=None, measures_during=None,
        special_conditions=None, ppe_text=None, members=[], briefing=None,
        daily_admissions=[], extensions=[], completion=None, closed_at=None, signatures=[],
    )
    out = build_work_permit_docx(data)
    assert isinstance(out, bytes) and len(out) > 0


def test_label_dicts_cover_lifecycle_vocab():
    from app.domains.work_permits import lifecycle as lc
    from app.domains.work_permits import print_form as pf
    assert set(pf.WORK_TYPE_LABELS) >= lc.WORK_TYPES
    assert set(pf.MEMBER_ROLE_LABELS) >= lc.MEMBER_ROLES
    assert set(pf.SAFETY_SYSTEM_LABELS) >= lc.SAFETY_SYSTEMS
    assert set(pf.STATUS_LABELS) >= lc.WORK_PERMIT_STATUSES
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_form.py -q`
Expected: FAIL (`TypeError` — у `WorkPermitPrintData` нет `legal_reference`/`structured_section`; `ImportError` на `StructuredSection`).

- [ ] **Step 3: Реализовать generic-секцию и legal_reference в `print_form.py`**

В `print_form.py`: (а) добавить датаклассы; (б) в `WorkPermitPrintData` заменить `safety_systems_labels: list[str]` на `structured_section: "StructuredSection | None"` и добавить `legal_reference: str` (сразу после `work_type_label`); (в) обновить заголовок и блок «Описание работ».

Добавить датаклассы (после `SignatureLine`):
```python
@dataclass
class StructuredTable:
    headers: list[str]
    rows: list[list[str]]


@dataclass
class StructuredSection:
    title: str
    kv: list[tuple[str, str]]
    table: "StructuredTable | None"
```

В `WorkPermitPrintData` заменить поле:
```python
    work_type_label: str
    legal_reference: str          # приказ/правила (из профиля вида работ)
    status_label: str
```
и убрать строку `safety_systems_labels: list[str]`, добавив вместо неё (на месте, где была):
```python
    structured_section: "StructuredSection | None"
```

Заголовок (заменить хардкод):
```python
    doc.add_heading(
        f"НАРЯД-ДОПУСК на производство работ повышенной опасности "
        f"({data.work_type_label}, {data.legal_reference})", level=0,
    )
```

В блоке «3. Описание работ» убрать строку `_kv(doc, "Системы обеспечения безопасности", ...)` и ПОСЛЕ блока описания (перед «4. Целевой инструктаж») вставить рендер структурной секции:
```python
    # 3b. Структурная секция вида работ (системы безопасности / газоанализ / …)
    sec = data.structured_section
    if sec is not None:
        doc.add_heading(sec.title, level=1)
        for label, value in sec.kv:
            _kv(doc, label, value)
        if sec.table is not None and sec.table.rows:
            tbl = doc.add_table(rows=1, cols=len(sec.table.headers))
            tbl.style = "Table Grid"
            for i, h in enumerate(sec.table.headers):
                tbl.rows[0].cells[i].text = h
            for row in sec.table.rows:
                cells = tbl.add_row().cells
                for i, val in enumerate(row):
                    cells[i].text = str(val)
```

- [ ] **Step 4: Прогнать тест — убедиться, что зелено**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_form.py -q`
Expected: PASS (4 теста).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/print_form.py tests/test_work_permit_print_form.py
git commit -m "feat(work-permits): generic StructuredSection + legal_reference в печатном бланке (T1)"
```

---

## Task 2: Модуль профилей `profiles.py`

Чистый реестр: приказ, вид секции, валидация `type_specific`, сборка печатной секции.

**Files:**
- Create: `backend/app/domains/work_permits/profiles.py`
- Test: `tests/test_work_permit_profiles.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Профили видов работ: приказ, валидация type_specific, сборка печатной секции."""
from __future__ import annotations

import pytest

from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import profiles as pr
from app.domains.work_permits.print_form import StructuredSection


def test_registry_covers_all_work_types():
    assert set(pr.PROFILES) == set(lc.WORK_TYPES)


def test_legal_reference_per_type():
    assert "782н" in pr.legal_reference("height")
    assert "902н" in pr.legal_reference("confined_space")
    assert "903н" in pr.legal_reference("electrical")
    assert "1479" in pr.legal_reference("hot_work")


def test_validate_confined_accepts_valid_payload():
    pr.validate_type_specific("confined_space", {
        "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
        "ventilation": "forced",
    })  # не бросает


def test_validate_confined_rejects_unknown_key():
    with pytest.raises(ValueError):
        pr.validate_type_specific("confined_space", {"bogus": 1})


def test_validate_confined_rejects_bad_parameter():
    with pytest.raises(ValueError):
        pr.validate_type_specific("confined_space", {"gas_analysis": [{"parameter": "xx", "value": "1"}]})


def test_validate_confined_rejects_bad_ventilation():
    with pytest.raises(ValueError):
        pr.validate_type_specific("confined_space", {"ventilation": "turbo"})


def test_validate_none_profile_rejects_nonempty():
    # вид без структурной секции (electrical) не принимает type_specific
    with pytest.raises(ValueError):
        pr.validate_type_specific("electrical", {"gas_analysis": []})


def test_validate_height_rejects_type_specific():
    # высота держит safety_systems-колонку, type_specific должен быть пуст
    with pytest.raises(ValueError):
        pr.validate_type_specific("height", {"ventilation": "forced"})


def test_validate_allows_none_and_empty():
    pr.validate_type_specific("confined_space", None)
    pr.validate_type_specific("electrical", None)
    pr.validate_type_specific("confined_space", {})


def test_build_section_height_from_safety_systems():
    sec = pr.build_structured_section("height", safety_systems=["restraint", "fall_arrest"], type_specific=None)
    assert isinstance(sec, StructuredSection)
    assert "Удерживающие" in sec.kv[0][1] and "Страховочные" in sec.kv[0][1]
    assert sec.table is None


def test_build_section_confined_from_type_specific():
    sec = pr.build_structured_section(
        "confined_space", safety_systems=None,
        type_specific={"gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
                       "ventilation": "forced"})
    assert isinstance(sec, StructuredSection)
    assert any("Вентиляция" == k for k, _ in sec.kv)
    assert sec.table is not None and sec.table.rows[0][0] == "Кислород (O₂), %"


def test_build_section_none_profile_returns_none():
    assert pr.build_structured_section("electrical", safety_systems=None, type_specific=None) is None
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_profiles.py -q`
Expected: FAIL (`ModuleNotFoundError: profiles`).

- [ ] **Step 3: Реализовать `profiles.py`**

```python
"""Профили видов работ наряда-допуска: приказ, структурная секция, валидация.

Чистый модуль (без I/O / без sqlalchemy) — как lifecycle.py. Полиморфный шов
per-type специфики: legal_reference, словари структурной секции, валидация
type_specific, сборка печатной StructuredSection. Высота читает колонку
safety_systems; ОЗП — type_specific JSON.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.domains.work_permits import print_form as pf

# --- словари структурной секции ОЗП (902н) ---
GAS_PARAMETERS = {
    "oxygen": "Кислород (O₂), %",
    "flammable": "Горючие газы и пары, % НКПР",
    "harmful": "Вредные вещества, мг/м³",
}
VENTILATION_MODES = {
    "natural": "Естественная",
    "forced": "Принудительная",
    "none": "Не применяется",
    "not_required": "Не требуется",
}
_GAS_KEYS = {"parameter", "value", "norm", "measured_at"}


@dataclass(frozen=True)
class WorkTypeProfile:
    code: str
    label: str
    legal_reference: str
    structured_kind: str | None   # "safety_systems" | "confined_env" | None


PROFILES: dict[str, WorkTypeProfile] = {
    "height": WorkTypeProfile(
        "height", "Работа на высоте",
        "Приказ Минтруда России от 16.11.2020 № 782н", "safety_systems"),
    "confined_space": WorkTypeProfile(
        "confined_space", "Работа в ограниченных и замкнутых пространствах",
        "Приказ Минтруда России от 15.12.2020 № 902н", "confined_env"),
    "electrical": WorkTypeProfile(
        "electrical", "Работа в электроустановках",
        "Приказ Минтруда России от 15.12.2020 № 903н", None),
    "hot_work": WorkTypeProfile(
        "hot_work", "Огневые работы",
        "Постановление Правительства РФ от 16.09.2020 № 1479 (ППР)", None),
    "gas_hazardous": WorkTypeProfile(
        "gas_hazardous", "Газоопасные работы",
        "Правила проведения газоопасных работ", None),
    "excavation": WorkTypeProfile(
        "excavation", "Земляные работы",
        "Правила безопасности при производстве земляных работ", None),
}

_GENERIC = WorkTypeProfile("generic", "Работы повышенной опасности",
                           "Правила по охране труда", None)


def profile_for(work_type: str) -> WorkTypeProfile:
    return PROFILES.get(work_type, _GENERIC)


def legal_reference(work_type: str) -> str:
    return profile_for(work_type).legal_reference


def validate_type_specific(work_type: str, payload: dict | None) -> None:
    """Raise ValueError если type_specific не соответствует профилю вида работ.

    None/пустой — всегда ок. Виды без структурной секции (structured_kind != confined_env)
    не принимают непустой payload (включая height — он использует safety_systems-колонку).
    """
    if not payload:
        return
    kind = profile_for(work_type).structured_kind
    if kind != "confined_env":
        raise ValueError(f"type_specific is not accepted for work_type {work_type!r}")
    unknown = set(payload) - {"gas_analysis", "ventilation"}
    if unknown:
        raise ValueError(f"unknown type_specific keys: {sorted(unknown)}")
    vent = payload.get("ventilation")
    if vent is not None and vent not in VENTILATION_MODES:
        raise ValueError(f"invalid ventilation: {vent!r}")
    rows = payload.get("gas_analysis")
    if rows is not None:
        if not isinstance(rows, list):
            raise ValueError("gas_analysis must be a list")
        for r in rows:
            if not isinstance(r, dict):
                raise ValueError("gas_analysis row must be an object")
            bad = set(r) - _GAS_KEYS
            if bad:
                raise ValueError(f"unknown gas_analysis keys: {sorted(bad)}")
            if r.get("parameter") not in GAS_PARAMETERS:
                raise ValueError(f"invalid gas parameter: {r.get('parameter')!r}")


def build_structured_section(
    work_type: str, *, safety_systems: list[str] | None, type_specific: dict | None,
):
    """Собрать печатную StructuredSection по профилю (или None)."""
    kind = profile_for(work_type).structured_kind
    if kind == "safety_systems":
        if not safety_systems:
            return None
        labels = ", ".join(pf.safety_system_label(c) for c in safety_systems)
        return pf.StructuredSection(
            title="Системы обеспечения безопасности (782н)",
            kv=[("Системы", labels)], table=None)
    if kind == "confined_env":
        ts = type_specific or {}
        kv: list[tuple[str, str]] = []
        vent = ts.get("ventilation")
        if vent:
            kv.append(("Вентиляция", VENTILATION_MODES.get(vent, vent)))
        rows = ts.get("gas_analysis") or []
        table = None
        if rows:
            table = pf.StructuredTable(
                headers=["Параметр", "Значение", "Норма", "Замер"],
                rows=[[GAS_PARAMETERS.get(r.get("parameter"), r.get("parameter") or ""),
                       str(r.get("value") or ""), str(r.get("norm") or ""),
                       str(r.get("measured_at") or "")] for r in rows])
        if not kv and table is None:
            return None
        return pf.StructuredSection(
            title="Анализ воздушной среды и вентиляция (902н)", kv=kv, table=table)
    return None
```

- [ ] **Step 4: Прогнать — убедиться, что зелено**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_profiles.py -q`
Expected: PASS (12 тестов).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/profiles.py tests/test_work_permit_profiles.py
git commit -m "feat(work-permits): реестр профилей видов работ (приказ/секция/валидация) (T2)"
```

---

## Task 3: Колонка `type_specific` + миграция wp06

**Files:**
- Modify: `backend/app/models/work_permit.py`
- Create: `backend/app/migrations/versions/20260621_wp06_work_permit_type_specific.py`
- Test: `tests/test_work_permit_type_specific_migration.py`

- [ ] **Step 1: Написать guard-тест миграции**

```python
"""wp06 guard: цепочка от wp05, колонка type_specific, honest downgrade."""
from __future__ import annotations

import importlib.util
from pathlib import Path

MIG = (
    Path(__file__).resolve().parents[1]
    / "backend/app/migrations/versions/20260621_wp06_work_permit_type_specific.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wp06_mig", MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_wp06_chain_and_revision():
    mod = _load()
    assert mod.revision == "20260621_wp06_work_permit_type_specific"
    assert mod.down_revision == "20260620_wp05_work_permit_closing"


def test_wp06_adds_type_specific_column():
    src = MIG.read_text(encoding="utf-8")
    assert '"work_permit"' in src           # table name LITERAL (AST-audit blindspot)
    assert "type_specific" in src


def test_wp06_downgrade_drops_column():
    src = MIG.read_text(encoding="utf-8")
    assert 'op.drop_column("work_permit", "type_specific")' in src
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_type_specific_migration.py -q`
Expected: FAIL (файла миграции нет → `FileNotFoundError`/import).

- [ ] **Step 3: Создать миграцию**

`backend/app/migrations/versions/20260621_wp06_work_permit_type_specific.py`:
```python
"""wp06: type_specific JSON на work_permit (additive) — структурная секция вида работ.

Generic-колонка под per-type секции (ОЗП газоанализ/вентиляция и т.д.); высота
держит safety_systems и не трогается. Имя таблицы ЛИТЕРАЛОМ (AST-audit blindspot).
Honest downgrade удаляет колонку.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260621_wp06_work_permit_type_specific"
down_revision = "20260620_wp05_work_permit_closing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_permit", sa.Column("type_specific", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_permit", "type_specific")
```

- [ ] **Step 4: Добавить колонку в ORM-модель**

В `backend/app/models/work_permit.py`, в классе `WorkPermit`, после строки `safety_systems: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)` добавить:
```python
    type_specific: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 5: Прогнать guard — убедиться, что зелено**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_type_specific_migration.py -q`
Expected: PASS (3 теста).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/work_permit.py backend/app/migrations/versions/20260621_wp06_work_permit_type_specific.py tests/test_work_permit_type_specific_migration.py
git commit -m "feat(work-permits): колонка type_specific + миграция wp06 (T3)"
```

---

## Task 4: Схемы — поле `type_specific` + валидация create

**Files:**
- Modify: `backend/app/schemas/work_permit.py`
- Test: `backend/tests/test_work_permit_confined_schemas.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Валидация type_specific в схемах наряда-допуска (ОЗП 902н)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.work_permit import WorkPermitCreate


def _base(**extra):
    return {"work_type": "confined_space", "zone_text": "колодец К-12", **extra}


def test_create_accepts_valid_confined_type_specific():
    m = WorkPermitCreate(**_base(type_specific={
        "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
        "ventilation": "forced",
    }))
    assert m.type_specific["ventilation"] == "forced"


def test_create_rejects_bad_parameter():
    with pytest.raises(ValidationError):
        WorkPermitCreate(**_base(type_specific={"gas_analysis": [{"parameter": "xx", "value": "1"}]}))


def test_create_rejects_type_specific_on_height():
    with pytest.raises(ValidationError):
        WorkPermitCreate(work_type="height", zone_text="фасад",
                         type_specific={"ventilation": "forced"})


def test_create_allows_no_type_specific():
    m = WorkPermitCreate(**_base())
    assert m.type_specific is None
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_confined_schemas.py -q`
Expected: FAIL (`WorkPermitCreate` не имеет `type_specific`).

- [ ] **Step 3: Добавить поле и валидатор в схемы**

В `backend/app/schemas/work_permit.py`:
- импорт сверху: заменить `from pydantic import field_validator` на `from pydantic import field_validator, model_validator`; добавить `from app.domains.work_permits import profiles as wp_profiles`.
- В `WorkPermitCreate` добавить поле (после `ppe_text`):
```python
    type_specific: dict | None = None
```
и метод-валидатор (после `_safety_systems`):
```python
    @model_validator(mode="after")
    def _type_specific(self):
        try:
            wp_profiles.validate_type_specific(self.work_type, self.type_specific)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        return self
```
- В `WorkPermitUpdate` добавить поле (после `ppe_text`):
```python
    type_specific: dict | None = None
```
  (кросс-валидация update — на уровне роута, т.к. `work_type` может быть None; см. Task 7.)
- В `WorkPermitRead` добавить поле (после `ppe_text`):
```python
    type_specific: dict | None
```

- [ ] **Step 4: Прогнать — убедиться, что зелено**

Run: `.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_confined_schemas.py -q`
Expected: PASS (4 теста).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/work_permit.py backend/tests/test_work_permit_confined_schemas.py
git commit -m "feat(work-permits): type_specific в схемах + валидация create через профиль (T4)"
```

---

## Task 5: Сервис CRUD — `type_specific` в create/update

**Files:**
- Modify: `backend/app/domains/work_permits/service.py`
- Test: `tests/test_work_permit_service.py` (добавить кейс)

- [ ] **Step 1: Добавить падающий тест в `tests/test_work_permit_service.py`**

Дописать в конец файла (ориентируйся на существующий стиль `_persons`/`sessionmaker`/`data_factory` в файле; если хелпер создания персон называется иначе — переиспользуй его):
```python
@pytest.mark.asyncio
async def test_create_and_edit_persists_type_specific(sessionmaker, data_factory):
    tenant = await data_factory.ensure_tenant()
    tid = str(tenant.id)
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=tid, work_type="confined_space", zone_text="колодец",
            type_specific={"ventilation": "forced"})
        assert wp.type_specific == {"ventilation": "forced"}
        edited = await svc.update_work_permit(
            session, tenant_id=tid, work_permit_id=wp.id,
            type_specific={"ventilation": "natural"})
        assert edited.type_specific == {"ventilation": "natural"}
```
(Убедись, что файл импортирует `pytest` и `from app.domains.work_permits import service as svc` — если нет, добавь.)

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_service.py::test_create_and_edit_persists_type_specific -q`
Expected: FAIL (`create_work_permit` не принимает `type_specific`).

- [ ] **Step 3: Пробросить `type_specific` в сервисе**

В `backend/app/domains/work_permits/service.py`:
- В сигнатуру `create_work_permit` добавить kwarg (после `ppe_text: str | None = None,`):
```python
    type_specific: dict | None = None,
```
- В конструктор `WorkPermit(...)` добавить (после `ppe_text=ppe_text,`):
```python
        type_specific=type_specific,
```
- В кортеж `_DRAFT_EDITABLE` добавить `"type_specific"` (в конец).

- [ ] **Step 4: Прогнать — убедиться, что зелено**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_service.py::test_create_and_edit_persists_type_specific -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/service.py tests/test_work_permit_service.py
git commit -m "feat(work-permits): type_specific в CRUD-сервисе (T5)"
```

---

## Task 6: Сервис печати — `legal_reference` + `structured_section` через профиль

**Files:**
- Modify: `backend/app/services/work_permit_print.py`
- Test: `tests/test_work_permit_print_service.py` (добавить ОЗП-кейс)

- [ ] **Step 1: Добавить падающий ОЗП-тест в `tests/test_work_permit_print_service.py`**

Дописать в конец файла:
```python
@pytest.mark.asyncio
async def test_render_confined_space_uses_902n_and_gas_table(sessionmaker, data_factory):
    tenant, (foreman,) = await _persons(data_factory, "Sidor")
    tid = str(tenant.id)
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=tid, work_type="confined_space", zone_text="колодец К-12",
            number="НД-ОЗП-1",
            type_specific={"gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
                           "ventilation": "forced"})
        await svc.add_member(session, tenant_id=tid, work_permit_id=wp.id,
                             person_id=foreman.id, role="foreman")
        rendered = await render_work_permit(session, tenant=tenant, permit_id=wp.id,
                                            fmt="docx", with_letterhead=False)
        text = _docx_text(rendered.content)
        assert "902н" in text                       # приказ ОЗП в шапке
        assert "Принудительная" in text             # вентиляция
        assert "Кислород" in text and "20.9" in text  # таблица газоанализа
        assert "782н" not in text                    # высотный приказ не протёк
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_service.py::test_render_confined_space_uses_902n_and_gas_table -q`
Expected: FAIL (`WorkPermitPrintData` теперь требует `legal_reference`/`structured_section`, которые сервис ещё не передаёт → `TypeError`).

- [ ] **Step 3: Подключить профиль в сервисе**

В `backend/app/services/work_permit_print.py`:
- добавить импорт (рядом с `from app.domains.work_permits import print_form as pf`):
```python
from app.domains.work_permits import profiles as wp_profiles
```
- В конструкторе `pf.WorkPermitPrintData(...)`: добавить после `work_type_label=pf.work_type_label(wp.work_type),` строку:
```python
        legal_reference=wp_profiles.legal_reference(wp.work_type),
```
- Заменить строку `safety_systems_labels=[pf.safety_system_label(c) for c in (wp.safety_systems or [])],` на:
```python
        structured_section=wp_profiles.build_structured_section(
            wp.work_type, safety_systems=wp.safety_systems, type_specific=wp.type_specific),
```

- [ ] **Step 4: Прогнать ОЗП-кейс + регресс высоты — убедиться, что зелено**

Run: `.venv\Scripts\python.exe -m pytest tests/test_work_permit_print_service.py -q`
Expected: PASS (3 теста — включая существующий высотный `test_render_docx_includes_members_and_signature`).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/work_permit_print.py tests/test_work_permit_print_service.py
git commit -m "feat(work-permits): печать через профиль вида работ (legal_reference + секция) (T6)"
```

---

## Task 7: Роуты — проброс `type_specific` + 422-валидация update

**Files:**
- Modify: `backend/app/api/routes/work_permits.py`
- Test: `tests/api/test_work_permit_782n_fields.py` (добавить кейсы) — если структура файла иная, создай `tests/api/test_work_permit_confined_api.py` с теми же тестами.

- [ ] **Step 1: Написать падающий API-тест**

Добавить (в `tests/api/test_work_permit_782n_fields.py` рядом с существующими, либо новый файл `tests/api/test_work_permit_confined_api.py`). Ориентируйся на существующий в файле паттерн клиента/заголовков (`client`, tenant-заголовок); ниже — каркас, адаптируй фикстуры под файл:
```python
@pytest.mark.asyncio
async def test_create_confined_permit_with_type_specific(client, tenant_headers):
    body = {"work_type": "confined_space", "zone_text": "колодец",
            "type_specific": {"ventilation": "forced",
                              "gas_analysis": [{"parameter": "oxygen", "value": "20.9"}]}}
    r = await client.post("/work-permits", json=body, headers=tenant_headers)
    assert r.status_code == 201, r.text
    assert r.json()["type_specific"]["ventilation"] == "forced"


@pytest.mark.asyncio
async def test_create_confined_rejects_bad_ventilation(client, tenant_headers):
    body = {"work_type": "confined_space", "zone_text": "колодец",
            "type_specific": {"ventilation": "turbo"}}
    r = await client.post("/work-permits", json=body, headers=tenant_headers)
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_patch_type_specific_validated_against_persisted_type(client, tenant_headers):
    created = await client.post("/work-permits",
                                json={"work_type": "confined_space", "zone_text": "колодец"},
                                headers=tenant_headers)
    wp_id = created.json()["id"]
    bad = await client.patch(f"/work-permits/{wp_id}",
                             json={"type_specific": {"ventilation": "turbo"}},
                             headers=tenant_headers)
    assert bad.status_code == 422, bad.text
```

- [ ] **Step 2: Прогнать — убедиться, что падает**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_work_permit_782n_fields.py -k confined -q`
Expected: FAIL (create не пробрасывает `type_specific`; patch не валидирует → не 422).

- [ ] **Step 3: Пробросить и провалидировать в роуте**

В `backend/app/api/routes/work_permits.py`:
- В `_permit_read(...)` (конструктор `WorkPermitRead`) добавить после `ppe_text=wp.ppe_text,`:
```python
        type_specific=wp.type_specific,
```
- В `create_work_permit_endpoint`, в вызове `create_work_permit(...)` добавить после `special_conditions_text=payload.special_conditions_text, ppe_text=payload.ppe_text,`:
```python
        type_specific=payload.type_specific,
```
- В `update_work_permit_endpoint`, добавить импорт профиля сверху файла (рядом с прочими `from app.domains.work_permits ...`):
```python
from app.domains.work_permits import profiles as wp_profiles
```
  и валидацию ПЕРЕД вызовом `update_work_permit` (после блока проверки `site_id`, до `try:`):
```python
    if "type_specific" in fields:
        effective_type = fields.get("work_type") or (
            await _get_or_404(session, tenant, wp_id)).work_type
        try:
            wp_profiles.validate_type_specific(effective_type, fields["type_specific"])
        except ValueError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
```

- [ ] **Step 4: Прогнать — убедиться, что зелено**

Run: `.venv\Scripts\python.exe -m pytest tests/api/test_work_permit_782n_fields.py -k confined -q`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/work_permits.py tests/api/test_work_permit_782n_fields.py
git commit -m "feat(work-permits): API проброс type_specific + 422-валидация update (T7)"
```

---

## Task 8: Demo-seed ОЗП-наряда

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`

- [ ] **Step 1: Добавить seed-функцию**

В `backend/app/services/demo_bootstrap.py` добавить функцию рядом с `_seed_briefing_code_flow_demo` (нужны импорты `WorkPermit`, `WorkPermitMember` из `app.models.work_permit` — добавить к существующим импортам сверху файла):
```python
async def _seed_work_permit_confined_demo(session, tenant_db_id: str, person) -> None:
    """Демо-наряд ОЗП (902н) с газоанализом — печатается «из коробки». Идемпотентно."""
    from app.models.work_permit import WorkPermit, WorkPermitMember

    wp = (await session.execute(select(WorkPermit).where(
        WorkPermit.tenant_id == tenant_db_id, WorkPermit.number == "WP-OZP-DEMO",
    ))).scalar_one_or_none()
    if wp is None:
        wp = WorkPermit(
            tenant_id=tenant_db_id, number="WP-OZP-DEMO", work_type="confined_space",
            zone_text="Колодец К-12, насосная станция", status="draft",
            type_specific={
                "gas_analysis": [{"parameter": "oxygen", "value": "20.9", "norm": "≥ 20"}],
                "ventilation": "forced",
            },
        )
        session.add(wp)
        await session.flush()
    member = (await session.execute(select(WorkPermitMember).where(
        WorkPermitMember.tenant_id == tenant_db_id,
        WorkPermitMember.work_permit_id == wp.id, WorkPermitMember.person_id == person.id,
        WorkPermitMember.role == "foreman",
    ))).scalar_one_or_none()
    if member is None:
        session.add(WorkPermitMember(
            tenant_id=tenant_db_id, work_permit_id=wp.id, person_id=person.id, role="foreman"))
```

- [ ] **Step 2: Вызвать seed из `bootstrap_demo_tenant`**

Найти в `bootstrap_demo_tenant` место, где уже вызывается `_seed_briefing_code_flow_demo(session, tenant_db_id, person)` (демо-person в скоупе), и сразу после него добавить:
```python
        await _seed_work_permit_confined_demo(session, tenant_db_id, person)
```
(если вызов briefing-seed отсутствует/в другом скоупе — поставить вызов там, где доступны `session`, `tenant_db_id` и демо-`person` тенант-схемы.)

- [ ] **Step 3: Проверить smoke-импортом, что модуль грузится**

Run: `.venv\Scripts\python.exe -c "import app.services.demo_bootstrap"`
Expected: без ошибок (exit 0).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/demo_bootstrap.py
git commit -m "feat(work-permits): demo-seed ОЗП-наряда с газоанализом (T8)"
```

---

## Task 9: Фронтенд — типы, словари, условная секция формы, деталь

**Files:**
- Modify: `frontend/src/lib/workPermitVocab.ts`, `frontend/src/types/dto/workPermits.ts`, `frontend/src/types/forms/workPermits.ts`, `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`, `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx`
- Test: `frontend/src/__tests__/WorkPermitConfinedForm.test.tsx`

- [ ] **Step 1: Словари в `workPermitVocab.ts`**

Добавить в конец `frontend/src/lib/workPermitVocab.ts` (перед `labelOf`, если он последний — после него тоже ок):
```typescript
export const LEGAL_REFERENCE_LABELS: Record<string, string> = {
  height: "Приказ Минтруда № 782н",
  confined_space: "Приказ Минтруда № 902н",
  electrical: "Приказ Минтруда № 903н",
  hot_work: "Постановление Правительства РФ № 1479 (ППР)",
  gas_hazardous: "Правила газоопасных работ",
  excavation: "Правила земляных работ",
};

export const GAS_PARAMETER_LABELS: Record<string, string> = {
  oxygen: "Кислород (O₂), %",
  flammable: "Горючие газы и пары, % НКПР",
  harmful: "Вредные вещества, мг/м³",
};

export const VENTILATION_LABELS: Record<string, string> = {
  natural: "Естественная",
  forced: "Принудительная",
  none: "Не применяется",
  not_required: "Не требуется",
};
```

- [ ] **Step 2: Типы DTO/форм**

В `frontend/src/types/dto/workPermits.ts`, в интерфейс `WorkPermitDto` после `ppe_text: string | null;` добавить:
```typescript
  type_specific: Record<string, unknown> | null;
```

В `frontend/src/types/forms/workPermits.ts` добавить константы и поле схемы:
```typescript
export const GAS_PARAMETER_CODES = ["oxygen", "flammable", "harmful"] as const;
export const VENTILATION_CODES = ["natural", "forced", "none", "not_required"] as const;

const gasMeasurementSchema = z.object({
  parameter: z.enum(GAS_PARAMETER_CODES),
  value: z.string(),
  norm: z.string().optional(),
  measured_at: z.string().optional(),
});

export const confinedEnvSchema = z.object({
  gas_analysis: z.array(gasMeasurementSchema).optional(),
  ventilation: z.enum(VENTILATION_CODES).optional(),
});
export type ConfinedEnvValues = z.infer<typeof confinedEnvSchema>;
```
и в `workPermitSchema` после `ppe_text: z.string().optional(),` добавить:
```typescript
  type_specific: confinedEnvSchema.nullable().optional(),
```

- [ ] **Step 3: Написать падающий vitest**

`frontend/src/__tests__/WorkPermitConfinedForm.test.tsx`:
```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { WorkPermitFormDialog } from "@/features/work-permits/WorkPermitFormDialog";

vi.mock("@/api/workPermits", () => ({ workPermitsApi: { create: vi.fn(), update: vi.fn() } }));

describe("WorkPermitFormDialog confined section", () => {
  it("показывает секцию ОЗП при выборе confined_space и скрывает safety_systems", async () => {
    render(<WorkPermitFormDialog trigger={<button>open</button>} />);
    fireEvent.click(screen.getByText("open"));
    // по умолчанию height → видны системы безопасности
    expect(screen.getByText("Системы обеспечения безопасности")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Вид работ"), { target: { value: "confined_space" } });
    expect(screen.getByText(/Анализ воздушной среды/i)).toBeInTheDocument();
    expect(screen.queryByText("Системы обеспечения безопасности")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Прогнать — убедиться, что падает**

Run (в `frontend/`): `npm run test -- WorkPermitConfinedForm`
Expected: FAIL (секция ОЗП не рендерится; safety_systems показывается всегда).

- [ ] **Step 5: Условная секция в `WorkPermitFormDialog.tsx`**

В `frontend/src/features/work-permits/WorkPermitFormDialog.tsx`:
- В `EMPTY` добавить `type_specific: null,` (после `ppe_text: ""`).
- Импортировать словари: добавить `LEGAL_REFERENCE_LABELS, GAS_PARAMETER_LABELS, VENTILATION_LABELS` к существующему импорту из `@/lib/workPermitVocab`; и `GAS_PARAMETER_CODES, VENTILATION_CODES` к импорту из `@/types/forms/workPermits`.
- В `useEffect`-ресете initialData добавить `type_specific: (initialData.type_specific as WorkPermitFormValues["type_specific"]) ?? null,`.
- В `toBody` добавить ключ:
```typescript
    type_specific: v.work_type === "confined_space" ? (v.type_specific ?? null) : null,
```
- Сделать `DialogDescription` динамическим. Заменить:
```tsx
          <DialogDescription>Работа на высоте (форма 782н)</DialogDescription>
```
на (через `form.watch("work_type")`):
```tsx
          <DialogDescription>
            {WORK_TYPE_LABELS[form.watch("work_type")] ?? "Наряд-допуск"} ·{" "}
            {LEGAL_REFERENCE_LABELS[form.watch("work_type")] ?? ""}
          </DialogDescription>
```
- Блок `safety_systems` обернуть условием `height`, добавить ОЗП-блок. Заменить весь блок «Системы обеспечения безопасности» (`<div className="space-y-1">…safety_systems…</div>`) на:
```tsx
          {form.watch("work_type") === "height" && (
            <div className="space-y-1">
              <Label>Системы обеспечения безопасности</Label>
              <div className="flex flex-wrap gap-3">
                {SAFETY_SYSTEM_CODES.map((code) => (
                  <label key={code} className="flex items-center gap-2 text-sm">
                    <input type="checkbox" checked={selected.has(code)} onChange={() => toggleSystem(code)} />
                    {SAFETY_SYSTEM_LABELS[code]}
                  </label>
                ))}
              </div>
            </div>
          )}

          {form.watch("work_type") === "confined_space" && (
            <div className="space-y-2">
              <Label>Анализ воздушной среды и вентиляция (902н)</Label>
              <div className="space-y-1">
                <Label htmlFor="ventilation" className="text-xs">Вентиляция</Label>
                <select
                  id="ventilation"
                  className="h-10 w-full rounded-md border px-3"
                  value={(form.watch("type_specific")?.ventilation as string) ?? ""}
                  onChange={(e) =>
                    form.setValue("type_specific", {
                      ...(form.watch("type_specific") ?? {}),
                      ventilation: (e.target.value || undefined) as never,
                    })
                  }
                >
                  <option value="">—</option>
                  {VENTILATION_CODES.map((c) => (
                    <option key={c} value={c}>{VENTILATION_LABELS[c]}</option>
                  ))}
                </select>
              </div>
              <p className="text-xs text-muted-foreground">
                Параметры замеров: {GAS_PARAMETER_CODES.map((c) => GAS_PARAMETER_LABELS[c]).join(", ")}.
                Изоляция коммуникаций и средства эвакуации — в полях «Мероприятия» / «Особые условия».
              </p>
            </div>
          )}
```
(Газоанализ-строки в форме оставляем минимальными — вентиляция через select; полноценный табличный редактор замеров — follow-up; ключевое для тиража: секция параметризована по виду и сериализуется в `type_specific`.)

- [ ] **Step 6: Показ ОЗП-секции на деталь-странице**

В `frontend/src/pages/work-permits/WorkPermitDetailPage.tsx` добавить (в блоке отображения наряда, где показываются прочие поля; ориентируйся на существующий рендер `safety_systems`/полей) условный блок для `confined_space`:
```tsx
{wp.work_type === "confined_space" && wp.type_specific ? (
  <div className="text-sm">
    <div className="font-medium">Анализ воздушной среды и вентиляция (902н)</div>
    {(wp.type_specific as { ventilation?: string }).ventilation ? (
      <div>Вентиляция: {VENTILATION_LABELS[(wp.type_specific as { ventilation: string }).ventilation] ?? "—"}</div>
    ) : null}
    {((wp.type_specific as { gas_analysis?: Array<{ parameter: string; value: string }> }).gas_analysis ?? []).map((m, i) => (
      <div key={i}>{GAS_PARAMETER_LABELS[m.parameter] ?? m.parameter}: {m.value}</div>
    ))}
  </div>
) : null}
```
(импортировать `VENTILATION_LABELS, GAS_PARAMETER_LABELS` из `@/lib/workPermitVocab`.)

- [ ] **Step 7: Прогнать vitest + build**

Run (в `frontend/`): `npm run test -- WorkPermitConfinedForm && npm run build`
Expected: тест PASS; `tsc`/build зелёные.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/lib/workPermitVocab.ts frontend/src/types/dto/workPermits.ts frontend/src/types/forms/workPermits.ts frontend/src/features/work-permits/WorkPermitFormDialog.tsx frontend/src/pages/work-permits/WorkPermitDetailPage.tsx frontend/src/__tests__/WorkPermitConfinedForm.test.tsx
git commit -m "feat(work-permits): фронт — условная ОЗП-секция формы + словари + деталь (T9)"
```

---

## Task 10: Регресс-когорт + handoff

**Files:**
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новый handoff сверху)

- [ ] **Step 1: Прогнать контурный регресс-когорт (backend)**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_work_permit_profiles.py tests/test_work_permit_type_specific_migration.py backend/tests/test_work_permit_confined_schemas.py tests/test_work_permit_print_form.py tests/test_work_permit_print_service.py tests/test_work_permit_service.py tests/api/test_work_permit_782n_fields.py tests/api/test_work_permit_print_api.py -q
```
Expected: EXIT 0 (все зелёные; высотные кейсы не регрессировали).

- [ ] **Step 2: Прогнать смежный миграционный когорт**

Run: `.venv\Scripts\python.exe -m pytest -k "migration or downgrade or mapper" -q`
Expected: EXIT 0 (цепочка wp05→wp06 single-head; ORM↔миграция консистентны).

- [ ] **Step 3: Фронт build**

Run (в `frontend/`): `npm run build`
Expected: зелёный.

- [ ] **Step 4: Записать handoff**

Добавить новый раздел `## Last Agent Handoff (2026-06-21, …ОЗП 902н + слой профилей…)` в начало `AI_IMPLEMENTATION_REPORT.md` (после `# AI Implementation Report`), по образцу предыдущих: что построено, ревью-находки, тесты (EXIT), отложенное (табличный редактор газозамеров; тираж огневые/электро/газоопасные/земляные вглубь; группы электробезопасности 903н), Next (ветка стопкой поверх Ф4, merge = пользователя).

- [ ] **Step 5: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(work-permits): handoff — тираж на ОЗП 902н + слой профилей построен (T10)"
```

---

## Self-Review (выполнено при написании плана)

**1. Покрытие спека:**
- §2 профиль/реестр → Task 2 (+ guard полноты `set(PROFILES)==WORK_TYPES`).
- §3 `type_specific` + миграция wp06 → Task 3; форма/вокабуляр ОЗП → Task 2/4.
- §4 печать (legal_reference + StructuredSection) → Task 1 (рендерер) + Task 6 (сборка через профиль).
- §5 схемы + сервисы → Task 4 (схемы) + Task 5 (CRUD) + Task 7 (роуты).
- §6 фронт → Task 9.
- §7 demo-seed → Task 8.
- §8 тесты → распределены по таскам + Task 10 (когорт).
- §9 YAGNI/отложенное → отражено в Task 9 (минимальный редактор) и Task 10 (handoff).
- §10 ветка/merge → шапка плана + Task 10.

**2. Плейсхолдеры:** код во всех шагах полный; «адаптируй фикстуры под файл» в Task 5/7 — осознанная инструкция (точные имена фикстур API-клиента зависят от существующего conftest; тело тестов задано). Каркасы API-тестов помечены как адаптируемые под существующий клиент/заголовки файла.

**3. Согласованность типов:** `StructuredSection(title, kv, table)` / `StructuredTable(headers, rows)` — единые в Task 1/2/6. `validate_type_specific(work_type, payload)` и `build_structured_section(work_type, *, safety_systems, type_specific)` — единые сигнатуры в Task 2/4/6/7. `type_specific` — `dict|None` (бэкенд) / `Record<string,unknown>|null` (DTO) / `confinedEnvSchema.nullable().optional()` (форма) согласованы.

**Известное ограничение (осознанное):** табличный редактор газозамеров на фронте не строится (только вентиляция-select + подсказка) — параметризация секции по виду достигнута; полный редактор замеров — follow-up. Бэкенд принимает полный `gas_analysis` через API/seed.
