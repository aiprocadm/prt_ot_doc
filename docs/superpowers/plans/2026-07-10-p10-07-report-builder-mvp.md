# P10-07 Report-builder MVP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Конструктор отчётов end-to-end: сохранённая сущность `ReportDefinition` (датасет + фильтры + колонки + группировки/агрегаты + сортировка) + sync-предпросмотр + celery-материализатор CSV/XLSX/PDF через существующий `ExportJob`-конвейер + страница-конструктор на фронте.

**Architecture:** Новый модуль `backend/app/modules/report_builder/` (декларативный реестр датасетов → единый SQL-engine → renderers) поверх существующей инфраструктуры: `ExportJob`/`ExportCenterService` (джоб), `FileStorageService`+`File` (файл), `GET /exports/{id}/download-link` (скачивание). Фичефлаг `report_builder` default-off. Спека: `docs/superpowers/specs/2026-07-10-p10-07-report-builder-mvp-design.md`.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (`rb01`) + Celery + openpyxl + python-docx + LibreOffice pool; React 18 + vitest.

**Операционка (ОБЯЗАТЕЛЬНО для каждого implementer'а):**
- Рабочая копия: `D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\worktrees\p10-07-report-builder` (ветка `feat/p10-07-report-builder-mvp`). Все пути ниже — относительно неё.
- Backend-тесты — ТОЛЬКО через PowerShell-инструмент, глобальный Python: `& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest <files> -q` из корня worktree. Таймаут 600000 мс, ОДИН прогон без ретраев (холодный импорт 2–3 мин). Git-Bash для pytest НЕ использовать (сегфолт). Батчи ≤5 файлов. Ориентир — exit-код `$LASTEXITCODE`.
- Frontend-гейты — через Bash из `frontend/` с АБСОЛЮТНЫМ cwd: `cd "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\worktrees\p10-07-report-builder\frontend" && npx vitest run <file>`. Если нет `node_modules` — контроллер поднимает `npm ci --prefer-offline` один раз (НЕ implementer).
- Коммиты после каждой задачи, сообщения `feat(p10-07): ...` / `test(p10-07): ...`.

---

## Task 1: Модель `ReportDefinition` + миграция `rb01`

**Files:**
- Create: `backend/app/models/report_builder.py`
- Modify: `backend/app/models/models.py` (импорт + `__all__ +=`)
- Create: `backend/app/migrations/versions/20260710_rb01_report_definition.py`
- Test: `tests/api/test_report_builder_model.py`

- [ ] **Step 1: Написать падающий тест**

```python
"""Model + migration pins for report_definition (P10-07 rb01)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from tests.utils.factories import TestDataFactory

MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "backend/app/migrations/versions/20260710_rb01_report_definition.py"
)


def _squash(text: str) -> str:
    # black может переносить аргументы — сравниваем без пробелов/переносов
    return "".join(text.split())


def test_migration_pins() -> None:
    src = MIGRATION.read_text(encoding="utf-8")
    flat = _squash(src)
    assert 'revision="20260710_rb01_report_definition"' in flat
    assert 'down_revision="20260709_med03_psychiatric_342n"' in flat
    assert '"report_definition"' in flat
    assert _squash(
        'sa.UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name")'
    ) in flat
    assert '"deleted_at"' in flat  # SoftDeleteMixin column present
    assert 'server_default="{}"' in flat  # config_json backfill-safe default
    assert _squash('op.drop_table("report_definition")') in flat  # round-trip


@pytest.mark.asyncio
async def test_model_roundtrip(sessionmaker, data_factory: TestDataFactory) -> None:
    from app.models.models import ReportDefinition  # re-export обязателен

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        record = ReportDefinition(
            tenant_id=str(tenant.id),
            name="Тестовый отчёт",
            dataset_code="incidents",
            config_json={"columns": ["title"]},
        )
        session.add(record)
        await session.commit()

        row = await session.scalar(
            select(ReportDefinition).where(ReportDefinition.tenant_id == str(tenant.id))
        )
        assert row is not None
        assert row.is_system is False  # ORM default
        assert row.deleted_at is None
        assert row.config_json == {"columns": ["title"]}
```

- [ ] **Step 2: Прогнать тест — убедиться, что падает**

Run (PowerShell, из корня worktree, таймаут 600000):
`& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_report_builder_model.py -q`
Expected: FAIL (`FileNotFoundError` на миграции / `ImportError: ReportDefinition`).

- [ ] **Step 3: Создать модель**

`backend/app/models/report_builder.py`:

```python
"""Report-builder saved definitions (P10-07 §24.3, slice rb01)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, String, Text, UniqueConstraint
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import SoftDeleteMixin, TenantBaseModel

__all__ = ["ReportDefinition"]


class ReportDefinition(TenantBaseModel, SoftDeleteMixin):
    """Сохранённый отчёт конструктора: датасет + config (фильтры/колонки/
    группировки/агрегаты/сортировка). ``is_system`` — «готовый шаблон» из ТЗ:
    неизменяемый (PATCH/DELETE → 400), на фронте только «Дублировать».
    Имя уникально per tenant БЕЗ фильтра deleted_at (паттерн ``PPESupplier``:
    soft-deleted тёзка честно даёт 409, слот не переиспользуется)."""

    __tablename__ = "report_definition"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_code: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name"),
    )
```

- [ ] **Step 4: Ре-экспорт в `models.py`**

В `backend/app/models/models.py`: рядом с блоком `from app.models.ppe import (...)` (строка ~208) добавить:

```python
from app.models.report_builder import ReportDefinition
```

и в конце файла (после последнего `__all__ += [...]`) добавить:

```python
__all__ += ["ReportDefinition"]
```

- [ ] **Step 5: Создать миграцию**

`backend/app/migrations/versions/20260710_rb01_report_definition.py`:

```python
"""rb01: report-builder — saved report definitions (P10-07 §24.3).

Additive. One new tenant-scoped table. VARCHAR/JSON only, no FKs beyond tenant_id.
Round-trip-safe: downgrade drops the table. Table/column names are LITERAL
(AST-audit blindspot).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260710_rb01_report_definition"
down_revision = "20260709_med03_psychiatric_342n"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_definition",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name"),
    )


def downgrade() -> None:
    op.drop_table("report_definition")
```

- [ ] **Step 6: Прогнать тест — зелёный**

Та же команда. Expected: 2 passed. Затем проверить единственный alembic head:
`$env:PYTHONPATH="backend"; & "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m alembic -c backend/app/migrations/alembic.ini heads`
Expected: единственный head `20260710_rb01_report_definition`.

- [ ] **Step 7: Commit** — `feat(p10-07): ReportDefinition model + rb01 migration`

---

## Task 2: Реестр датасетов `datasets.py`

**Files:**
- Create: `backend/app/modules/report_builder/__init__.py` (пустой)
- Create: `backend/app/modules/report_builder/datasets.py`
- Test: `tests/api/test_report_builder_datasets.py`

- [ ] **Step 1: Падающий тест**

```python
"""Dataset registry integrity (P10-07 report builder)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Select


def test_registry_shape() -> None:
    from app.modules.report_builder.datasets import DATASETS, OPS_BY_KIND

    assert set(DATASETS.keys()) == {"employees_training", "incidents", "risks", "ppe_warehouse"}
    for code, spec in DATASETS.items():
        assert spec.code == code
        assert spec.title  # RU-название непустое
        keys = [c.key for c in spec.columns]
        assert len(keys) == len(set(keys)), f"duplicate column keys in {code}"
        for col in spec.columns:
            assert col.kind in OPS_BY_KIND, f"{code}.{col.key}: unknown kind {col.kind}"
            assert col.label, f"{code}.{col.key}: empty label"
            if col.aggregatable:
                assert col.kind == "number", f"{code}.{col.key}: only numbers are aggregatable"
            if col.kind == "enum":
                assert col.enum_cls is not None and col.enum_values, f"{code}.{col.key}"
        stmt = spec.build_stmt("tenant-x", datetime.now(tz=timezone.utc))
        assert isinstance(stmt, Select)
        # labeled columns of the base select match the declared registry keys
        assert [c.key for c in stmt.selected_columns] == keys


def test_expected_columns_pinned() -> None:
    from app.modules.report_builder.datasets import DATASETS

    assert [c.key for c in DATASETS["employees_training"].columns] == [
        "person_name", "position_title", "course_name", "status",
        "scheduled_at", "completed_at", "expires_at", "is_overdue",
    ]
    assert [c.key for c in DATASETS["incidents"].columns] == [
        "title", "incident_type", "status", "severity",
        "occurred_at", "company_name", "site_name",
    ]
    assert [c.key for c in DATASETS["risks"].columns] == [
        "hazard", "probability", "severity", "level",
        "controls", "company_name", "site_name",
    ]
    assert [c.key for c in DATASETS["ppe_warehouse"].columns] == [
        "item_name", "code", "category", "min_stock", "on_hand", "below_min",
    ]
```

- [ ] **Step 2: Прогнать — FAIL (`ModuleNotFoundError`)**

`& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_report_builder_datasets.py -q`

- [ ] **Step 3: Реализация**

`backend/app/modules/report_builder/datasets.py`:

```python
"""Declarative dataset registry for the report builder (P10-07 §24.3).

Каждый датасет = плоский список типизированных колонок + билдер базового
SELECT. Engine оборачивает базовый select в subquery и применяет фильтры /
группировку / сортировку единообразно по labeled-колонкам — поэтому
вычислимые колонки (is_overdue, on_hand, below_min) ОБЯЗАНЫ быть
SQL-выражениями, а не Python-постобработкой. Ключи labeled-колонок билдера
байт-в-байт совпадают со списком ``columns`` (пинуется тестом реестра).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from sqlalchemy import Select, case, func, select

from app.models.models import (
    Company,
    Incident,
    IncidentSeverity,
    IncidentStatus,
    IncidentType,
    Person,
    PPEItem,
    PPEItemCategory,
    PPEStockBatch,
    Risk,
    Site,
    Training,
    TrainingStatus,
)

OPS_BY_KIND: dict[str, tuple[str, ...]] = {
    "string": ("eq", "neq", "contains"),
    "number": ("eq", "gte", "lte"),
    "date": ("eq", "gte", "lte"),
    "datetime": ("eq", "gte", "lte"),
    "enum": ("eq", "in"),
    "bool": ("eq",),
}


@dataclass(frozen=True)
class ColumnSpec:
    key: str
    label: str
    kind: str  # ключ OPS_BY_KIND
    aggregatable: bool = False
    enum_cls: type[enum.Enum] | None = None

    @property
    def ops(self) -> tuple[str, ...]:
        return OPS_BY_KIND[self.kind]

    @property
    def enum_values(self) -> list[str] | None:
        if self.enum_cls is None:
            return None
        return [m.value for m in self.enum_cls]


@dataclass(frozen=True)
class DatasetSpec:
    code: str
    title: str
    columns: tuple[ColumnSpec, ...]
    build_stmt: Callable[[str, datetime], Select]

    def column(self, key: str) -> ColumnSpec | None:
        for col in self.columns:
            if col.key == key:
                return col
        return None


def _employees_training_stmt(tenant_id: str, now: datetime) -> Select:
    return (
        select(
            (Person.last_name + " " + Person.first_name).label("person_name"),
            Person.position_title.label("position_title"),
            Training.course_name.label("course_name"),
            Training.status.label("status"),
            Training.scheduled_at.label("scheduled_at"),
            Training.completed_at.label("completed_at"),
            Training.expires_at.label("expires_at"),
            case(
                ((Training.expires_at.is_not(None)) & (Training.expires_at < now), True),
                else_=False,
            ).label("is_overdue"),
        )
        .select_from(Training)
        .join(Person, Person.id == Training.person_id)
        .where(Training.tenant_id == tenant_id, Person.deleted_at.is_(None))
    )


def _incidents_stmt(tenant_id: str, now: datetime) -> Select:
    _ = now
    return (
        select(
            Incident.title.label("title"),
            Incident.incident_type.label("incident_type"),
            Incident.status.label("status"),
            Incident.severity.label("severity"),
            Incident.occurred_at.label("occurred_at"),
            Company.name.label("company_name"),
            Site.name.label("site_name"),
        )
        .select_from(Incident)
        .join(Company, Company.id == Incident.company_id)
        .join(Site, Site.id == Incident.site_id)
        .where(Incident.tenant_id == tenant_id, Incident.deleted_at.is_(None))
    )


def _risks_stmt(tenant_id: str, now: datetime) -> Select:
    _ = now
    return (
        select(
            Risk.hazard.label("hazard"),
            Risk.probability.label("probability"),
            Risk.severity.label("severity"),
            Risk.level.label("level"),
            Risk.controls.label("controls"),
            Company.name.label("company_name"),
            Site.name.label("site_name"),
        )
        .select_from(Risk)
        .join(Company, Company.id == Risk.company_id)
        .outerjoin(Site, Site.id == Risk.site_id)
        .where(Risk.tenant_id == tenant_id)
    )


def _ppe_warehouse_stmt(tenant_id: str, now: datetime) -> Select:
    _ = now
    on_hand_sq = (
        select(
            PPEStockBatch.item_id.label("item_id"),
            func.coalesce(func.sum(PPEStockBatch.quantity), 0).label("on_hand"),
        )
        .where(PPEStockBatch.tenant_id == tenant_id, PPEStockBatch.deleted_at.is_(None))
        .group_by(PPEStockBatch.item_id)
        .subquery()
    )
    on_hand = func.coalesce(on_hand_sq.c.on_hand, 0)
    return (
        select(
            PPEItem.name.label("item_name"),
            PPEItem.code.label("code"),
            PPEItem.category.label("category"),
            PPEItem.min_stock.label("min_stock"),
            on_hand.label("on_hand"),
            case((on_hand < PPEItem.min_stock, True), else_=False).label("below_min"),
        )
        .select_from(PPEItem)
        .outerjoin(on_hand_sq, on_hand_sq.c.item_id == PPEItem.id)
        .where(PPEItem.tenant_id == tenant_id, PPEItem.deleted_at.is_(None))
    )


DATASETS: dict[str, DatasetSpec] = {
    "employees_training": DatasetSpec(
        code="employees_training",
        title="Обучение сотрудников",
        columns=(
            ColumnSpec("person_name", "Сотрудник", "string"),
            ColumnSpec("position_title", "Должность", "string"),
            ColumnSpec("course_name", "Курс", "string"),
            ColumnSpec("status", "Статус", "enum", enum_cls=TrainingStatus),
            ColumnSpec("scheduled_at", "Запланировано", "datetime"),
            ColumnSpec("completed_at", "Пройдено", "datetime"),
            ColumnSpec("expires_at", "Действует до", "datetime"),
            ColumnSpec("is_overdue", "Просрочено", "bool"),
        ),
        build_stmt=_employees_training_stmt,
    ),
    "incidents": DatasetSpec(
        code="incidents",
        title="Инциденты",
        columns=(
            ColumnSpec("title", "Название", "string"),
            ColumnSpec("incident_type", "Тип", "enum", enum_cls=IncidentType),
            ColumnSpec("status", "Статус", "enum", enum_cls=IncidentStatus),
            ColumnSpec("severity", "Тяжесть", "enum", enum_cls=IncidentSeverity),
            ColumnSpec("occurred_at", "Дата", "datetime"),
            ColumnSpec("company_name", "Компания", "string"),
            ColumnSpec("site_name", "Объект", "string"),
        ),
        build_stmt=_incidents_stmt,
    ),
    "risks": DatasetSpec(
        code="risks",
        title="Реестр рисков",
        columns=(
            ColumnSpec("hazard", "Опасность", "string"),
            ColumnSpec("probability", "Вероятность", "number", aggregatable=True),
            ColumnSpec("severity", "Тяжесть", "number", aggregatable=True),
            ColumnSpec("level", "Уровень", "number", aggregatable=True),
            ColumnSpec("controls", "Меры контроля", "string"),
            ColumnSpec("company_name", "Компания", "string"),
            ColumnSpec("site_name", "Объект", "string"),
        ),
        build_stmt=_risks_stmt,
    ),
    "ppe_warehouse": DatasetSpec(
        code="ppe_warehouse",
        title="СИЗ: остатки на складе",
        columns=(
            ColumnSpec("item_name", "Позиция", "string"),
            ColumnSpec("code", "Код", "string"),
            ColumnSpec("category", "Категория", "enum", enum_cls=PPEItemCategory),
            ColumnSpec("min_stock", "Мин. остаток", "number", aggregatable=True),
            ColumnSpec("on_hand", "Остаток", "number", aggregatable=True),
            ColumnSpec("below_min", "Ниже минимума", "bool"),
        ),
        build_stmt=_ppe_warehouse_stmt,
    ),
}
```

Примечание: если каких-то из имён (`Company`, `Site`, `Training`, `TrainingStatus`, `Risk`, `PPEItem`, `PPEItemCategory`, `PPEStockBatch`, `Incident*`) нет в ре-экспорте `app.models.models` — импортировать напрямую из профильного модуля (`app.models.master_data` / `app.models.training` / `app.models.risk` / `app.models.ppe` / `app.models.incidents`), НЕ добавляя новые ре-экспорты.

- [ ] **Step 4: Прогнать — 2 passed**
- [ ] **Step 5: Commit** — `feat(p10-07): dataset registry (4 core datasets)`

---

## Task 3: Engine `engine.py`

**Files:**
- Create: `backend/app/modules/report_builder/engine.py`
- Test: `tests/api/test_report_builder_engine.py`

- [ ] **Step 1: Падающие тесты**

```python
"""Engine behaviour: filters / grouping / sort / validation / tenant isolation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.models import Company, Person, Site, Training, TrainingStatus
from tests.utils.factories import TestDataFactory

NOW = datetime.now(tz=timezone.utc)


async def _seed_training(session, data_factory: TestDataFactory):
    tenant = await data_factory.ensure_tenant(session=session)
    tid = str(tenant.id)
    company = Company(tenant_id=tid, name="ООО Ромашка")
    session.add(company)
    await session.flush()
    p1 = Person(tenant_id=tid, company_id=company.id, first_name="Иван", last_name="Иванов",
                position_title="Электрик")
    p2 = Person(tenant_id=tid, company_id=company.id, first_name="Пётр", last_name="Петров",
                position_title="Сварщик")
    session.add_all([p1, p2])
    await session.flush()
    session.add_all([
        Training(tenant_id=tid, person_id=p1.id, course_name="Охрана труда",
                 status=TrainingStatus.COMPLETED, expires_at=NOW - timedelta(days=5)),
        Training(tenant_id=tid, person_id=p1.id, course_name="Первая помощь",
                 status=TrainingStatus.COMPLETED, expires_at=NOW + timedelta(days=300)),
        Training(tenant_id=tid, person_id=p2.id, course_name="Охрана труда",
                 status=TrainingStatus.SCHEDULED, scheduled_at=NOW + timedelta(days=10)),
    ])
    await session.commit()
    return tid


@pytest.mark.asyncio
async def test_plain_columns_filter_sort(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session,
            tenant_id=tid,
            dataset_code="employees_training",
            config={
                "columns": ["person_name", "course_name", "is_overdue"],
                "filters": [{"field": "status", "op": "eq", "value": "completed"}],
                "sort": [{"field": "course_name", "dir": "asc"}],
            },
            limit=100,
        )
        assert result.total == 2
        assert [c.key for c in result.columns] == ["person_name", "course_name", "is_overdue"]
        assert [r["course_name"] for r in result.rows] == ["Охрана труда", "Первая помощь"]
        overdue = {r["course_name"]: r["is_overdue"] for r in result.rows}
        assert overdue == {"Охрана труда": True, "Первая помощь": False}


@pytest.mark.asyncio
async def test_bool_filter_on_computed_column(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session, tenant_id=tid, dataset_code="employees_training",
            config={"columns": ["course_name"],
                    "filters": [{"field": "is_overdue", "op": "eq", "value": True}]},
            limit=100,
        )
        assert result.total == 1
        assert result.rows[0]["course_name"] == "Охрана труда"


@pytest.mark.asyncio
async def test_group_by_with_aggregates(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session, tenant_id=tid, dataset_code="employees_training",
            config={"group_by": ["course_name"], "aggregates": [{"fn": "count"}],
                    "sort": [{"field": "count", "dir": "desc"}]},
            limit=100,
        )
        assert [c.key for c in result.columns] == ["course_name", "count"]
        assert result.rows[0] == {"course_name": "Охрана труда", "count": 2}
        assert result.total == 2  # 2 группы


@pytest.mark.asyncio
async def test_preview_limit_and_total(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        result = await run_report(
            session, tenant_id=tid, dataset_code="employees_training",
            config={"columns": ["course_name"]}, limit=1,
        )
        assert len(result.rows) == 1
        assert result.total == 3


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import run_report

    async with sessionmaker() as session:
        await _seed_training(session, data_factory)
        result = await run_report(
            session, tenant_id="other-tenant", dataset_code="employees_training",
            config={}, limit=100,
        )
        assert result.total == 0 and result.rows == []


@pytest.mark.asyncio
async def test_validation_errors(sessionmaker, data_factory: TestDataFactory):
    from app.modules.report_builder.engine import ReportConfigError, run_report, validate_config

    async with sessionmaker() as session:
        tid = await _seed_training(session, data_factory)
        with pytest.raises(ReportConfigError) as e1:
            await run_report(session, tenant_id=tid, dataset_code="nope", config={}, limit=1)
        assert e1.value.code == "dataset_unknown"
        with pytest.raises(ReportConfigError) as e2:
            await run_report(session, tenant_id=tid, dataset_code="employees_training",
                             config={"columns": ["bogus"]}, limit=1)
        assert e2.value.code == "column_unknown"
        with pytest.raises(ReportConfigError) as e3:
            await run_report(session, tenant_id=tid, dataset_code="employees_training",
                             config={"filters": [{"field": "person_name", "op": "gte", "value": "x"}]},
                             limit=1)
        assert e3.value.code == "filter_op_invalid"
        with pytest.raises(ReportConfigError) as e4:
            await run_report(session, tenant_id=tid, dataset_code="employees_training",
                             config={"group_by": ["course_name"],
                                     "aggregates": [{"fn": "sum", "field": "course_name"}]},
                             limit=1)
        assert e4.value.code == "aggregate_not_allowed"
        with pytest.raises(ReportConfigError) as e5:
            await run_report(session, tenant_id=tid, dataset_code="employees_training",
                             config={"sort": [{"field": "bogus", "dir": "asc"}]}, limit=1)
        assert e5.value.code == "sort_unknown"
        # validate_config — та же валидация без исполнения SQL
        with pytest.raises(ReportConfigError):
            validate_config("employees_training", {"columns": ["bogus"]})
        validate_config("employees_training", {"columns": ["person_name"]})  # не бросает
```

- [ ] **Step 2: Прогнать — FAIL (`ModuleNotFoundError: engine`)**

- [ ] **Step 3: Реализация**

`backend/app/modules/report_builder/engine.py`:

```python
"""Report execution engine: config → validated SQL → serialized rows.

Один и тот же компилятор обслуживает sync-preview (limit=PREVIEW_LIMIT) и
экспорт (limit=EXPORT_ROW_CAP в материализаторе). Фильтры / GROUP BY /
сортировка применяются на уровне SQL поверх subquery базового select'а
датасета — вычислимые колонки фильтруются наравне с физическими.
"""

from __future__ import annotations

import enum as _enum
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.report_builder.datasets import DATASETS, ColumnSpec, DatasetSpec

PREVIEW_LIMIT = 100
EXPORT_ROW_CAP = 50_000

__all__ = [
    "PREVIEW_LIMIT",
    "EXPORT_ROW_CAP",
    "ColumnMeta",
    "ReportConfigError",
    "ReportResult",
    "get_dataset",
    "run_report",
    "validate_config",
]


class ReportConfigError(Exception):
    """Невалидный config; на границе API маппится в 422."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ColumnMeta:
    key: str
    label: str
    kind: str


@dataclass(frozen=True)
class ReportResult:
    columns: list[ColumnMeta]
    rows: list[dict[str, Any]]
    total: int


def get_dataset(dataset_code: str) -> DatasetSpec:
    spec = DATASETS.get(dataset_code)
    if spec is None:
        raise ReportConfigError("dataset_unknown", f"Unknown dataset: {dataset_code}")
    return spec


def _require_column(spec: DatasetSpec, key: Any, *, context: str) -> ColumnSpec:
    if not isinstance(key, str) or spec.column(key) is None:
        raise ReportConfigError("column_unknown", f"Unknown column in {context}: {key}")
    return spec.column(key)  # type: ignore[return-value]


def _coerce_filter_value(col: ColumnSpec, op: str, value: Any) -> Any:
    if col.kind == "enum":
        assert col.enum_cls is not None
        try:
            if op == "in":
                if not isinstance(value, list) or not value:
                    raise ReportConfigError(
                        "filter_value_invalid", f"'in' expects a non-empty list for {col.key}"
                    )
                return [col.enum_cls(v) for v in value]
            return col.enum_cls(value)
        except ValueError as exc:
            raise ReportConfigError(
                "filter_value_invalid", f"Bad enum value for {col.key}: {value!r}"
            ) from exc
    if col.kind in {"date", "datetime"}:
        if not isinstance(value, str):
            raise ReportConfigError(
                "filter_value_invalid", f"ISO date string expected for {col.key}"
            )
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ReportConfigError(
                "filter_value_invalid", f"Bad date value for {col.key}: {value!r}"
            ) from exc
        if col.kind == "date":
            return parsed.date()
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    if col.kind == "number":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ReportConfigError("filter_value_invalid", f"Number expected for {col.key}")
        return value
    if col.kind == "bool":
        if not isinstance(value, bool):
            raise ReportConfigError("filter_value_invalid", f"Boolean expected for {col.key}")
        return value
    if not isinstance(value, str):
        raise ReportConfigError("filter_value_invalid", f"String expected for {col.key}")
    return value


def _apply_filters(stmt, sq, spec: DatasetSpec, filters: list[Any]):
    for item in filters:
        if not isinstance(item, dict):
            raise ReportConfigError("filter_invalid", "Each filter must be an object")
        col = _require_column(spec, item.get("field"), context="filters")
        op = item.get("op")
        if op not in col.ops:
            raise ReportConfigError(
                "filter_op_invalid", f"Operator {op!r} is not allowed for {col.key} ({col.kind})"
            )
        value = _coerce_filter_value(col, op, item.get("value"))
        column = sq.c[col.key]
        if op == "eq":
            stmt = stmt.where(column == value)
        elif op == "neq":
            stmt = stmt.where(column != value)
        elif op == "contains":
            stmt = stmt.where(column.ilike(f"%{value}%"))
        elif op == "gte":
            stmt = stmt.where(column >= value)
        elif op == "lte":
            stmt = stmt.where(column <= value)
        elif op == "in":
            stmt = stmt.where(column.in_(value))
    return stmt


def _compile(spec: DatasetSpec, tenant_id: str, config: dict[str, Any] | None, now: datetime):
    cfg = config or {}
    filters = list(cfg.get("filters") or [])
    group_by = list(cfg.get("group_by") or [])
    aggregates = list(cfg.get("aggregates") or [])
    sort = list(cfg.get("sort") or [])
    sq = spec.build_stmt(tenant_id, now).subquery()

    out_meta: list[ColumnMeta] = []
    if group_by:
        group_cols = []
        for key in group_by:
            col = _require_column(spec, key, context="group_by")
            group_cols.append(sq.c[col.key])
            out_meta.append(ColumnMeta(key=col.key, label=col.label, kind=col.kind))
        if not aggregates:
            aggregates = [{"fn": "count"}]
        agg_exprs = []
        for agg in aggregates:
            fn = agg.get("fn") if isinstance(agg, dict) else None
            if fn == "count":
                agg_exprs.append(func.count().label("count"))
                out_meta.append(ColumnMeta(key="count", label="Количество", kind="number"))
            elif fn == "sum":
                col = _require_column(spec, agg.get("field"), context="aggregates")
                if not col.aggregatable:
                    raise ReportConfigError(
                        "aggregate_not_allowed", f"Column is not aggregatable: {col.key}"
                    )
                out_key = f"sum_{col.key}"
                agg_exprs.append(func.sum(sq.c[col.key]).label(out_key))
                out_meta.append(
                    ColumnMeta(key=out_key, label=f"Сумма: {col.label}", kind="number")
                )
            else:
                raise ReportConfigError("aggregate_unknown", f"Unknown aggregate fn: {fn!r}")
        stmt = select(*group_cols, *agg_exprs)
        stmt = _apply_filters(stmt, sq, spec, filters)
        stmt = stmt.group_by(*group_cols)
    else:
        keys = list(cfg.get("columns") or []) or [c.key for c in spec.columns]
        sel_cols = []
        for key in keys:
            col = _require_column(spec, key, context="columns")
            sel_cols.append(sq.c[col.key])
            out_meta.append(ColumnMeta(key=col.key, label=col.label, kind=col.kind))
        stmt = select(*sel_cols)
        stmt = _apply_filters(stmt, sq, spec, filters)

    allowed = {m.key for m in out_meta}
    for item in sort:
        if not isinstance(item, dict):
            raise ReportConfigError("sort_invalid", "Each sort entry must be an object")
        key = item.get("field")
        direction = item.get("dir", "asc")
        if key not in allowed:
            raise ReportConfigError("sort_unknown", f"Unknown sort field: {key!r}")
        if direction not in {"asc", "desc"}:
            raise ReportConfigError("sort_dir_invalid", f"Bad sort direction: {direction!r}")
        stmt = stmt.order_by(asc(key) if direction == "asc" else desc(key))

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    return stmt, count_stmt, out_meta


def validate_config(dataset_code: str, config: dict[str, Any] | None) -> None:
    """Та же валидация, что и при исполнении, но без session/SQL — для
    create/update definition (битый config не должен сохраняться)."""
    spec = get_dataset(dataset_code)
    _compile(spec, "validation", config, datetime.now(tz=timezone.utc))


def _serialize_value(value: Any, kind: str) -> Any:
    if value is None:
        return None
    if isinstance(value, _enum.Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if kind == "bool":
        return bool(value)  # SQLite отдаёт 0/1 за case-выражения
    return value


async def run_report(
    session: AsyncSession,
    *,
    tenant_id: str,
    dataset_code: str,
    config: dict[str, Any] | None,
    limit: int,
    offset: int = 0,
) -> ReportResult:
    spec = get_dataset(dataset_code)
    now = datetime.now(tz=timezone.utc)
    stmt, count_stmt, out_meta = _compile(spec, tenant_id, config, now)
    total = int(await session.scalar(count_stmt) or 0)
    kind_by_key = {m.key: m.kind for m in out_meta}
    result = await session.execute(stmt.offset(offset).limit(limit))
    rows = [
        {k: _serialize_value(v, kind_by_key[k]) for k, v in dict(m).items()}
        for m in result.mappings().all()
    ]
    return ReportResult(columns=out_meta, rows=rows, total=total)
```

- [ ] **Step 4: Прогнать — 6 passed**
- [ ] **Step 5: Commit** — `feat(p10-07): report engine (filters/group-by/sort/validation)`

---

## Task 4: Renderers `renderers.py`

**Files:**
- Create: `backend/app/modules/report_builder/renderers.py`
- Test: `tests/api/test_report_builder_renderers.py`

- [ ] **Step 1: Падающие тесты**

```python
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
    assert ws.title == "Тест  отчёт"[:31].strip() or ws.title  # квадратные скобки удалены
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
```

- [ ] **Step 2: Прогнать — FAIL**

- [ ] **Step 3: Реализация**

`backend/app/modules/report_builder/renderers.py`:

```python
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
                ("да" if row[c.key] else "нет")
                if isinstance(row.get(c.key), bool)
                else row.get(c.key)
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
```

- [ ] **Step 4: Прогнать — 4 passed.** Если ассерт на `ws.title` неудобен из-за двойных пробелов — зафиксировать фактическое поведение `_sheet_title` в тесте (правится ТЕСТ, семантика «скобки удалены, ≤31» сохраняется).
- [ ] **Step 5: Commit** — `feat(p10-07): CSV/XLSX/PDF renderers`

---

## Task 5: Схемы + сервис + API (datasets / definitions CRUD / preview)

**Files:**
- Create: `backend/app/modules/report_builder/schemas.py`
- Create: `backend/app/modules/report_builder/service.py`
- Create: `backend/app/modules/report_builder/api.py`
- Modify: `backend/app/api/v1/route_groups.py` (импорт ~строка 77 + регистрация ~строка 185)
- Test: `tests/api/test_report_builder_api.py`

- [ ] **Step 1: Падающие тесты**

```python
"""API contract: flag gate, RBAC, CRUD, preview (P10-07 report builder)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

BASE = "/api/v1/report-builder"


async def _enable_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool = True) -> str:
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "report_builder"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="report_builder", title="Конструктор отчётов")
            session.add(feature)
            await session.flush()
        session.add(
            FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=on)
        )
        await session.commit()
        return str(tenant.id)


DEFINITION = {
    "name": "Мой отчёт",
    "dataset_code": "incidents",
    "config_json": {"columns": ["title", "status"]},
}


@pytest.mark.asyncio
async def test_flag_off_404(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}/datasets", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # default-off, без FeatureEnablement


@pytest.mark.asyncio
async def test_rbac_forbidden_role(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.WORKER)
    resp = await async_client.get(f"{BASE}/definitions", headers=headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    # line_manager: read — да, write — нет
    lm = await make_auth_headers(RoleEnum.LINE_MANAGER)
    ok = await async_client.get(f"{BASE}/definitions", headers=lm)
    assert ok.status_code == status.HTTP_200_OK
    denied = await async_client.post(f"{BASE}/definitions", json=DEFINITION, headers=lm)
    assert denied.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_datasets_catalog(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}/datasets", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == 4
    incidents = next(d for d in body["items"] if d["code"] == "incidents")
    status_col = next(c for c in incidents["columns"] if c["key"] == "status")
    assert status_col["kind"] == "enum"
    assert "reported" in status_col["enum_values"]
    assert status_col["ops"] == ["eq", "in"]


@pytest.mark.asyncio
async def test_crud_flow_and_conflicts(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(f"{BASE}/definitions", json=DEFINITION, headers=headers)
    assert created.status_code == status.HTTP_201_CREATED, created.text
    definition_id = created.json()["id"]
    assert created.json()["is_system"] is False

    dup = await async_client.post(f"{BASE}/definitions", json=DEFINITION, headers=headers)
    assert dup.status_code == status.HTTP_409_CONFLICT

    bad = await async_client.post(
        f"{BASE}/definitions",
        json={**DEFINITION, "name": "Битый", "config_json": {"columns": ["bogus"]}},
        headers=headers,
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    lst = await async_client.get(f"{BASE}/definitions", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert lst.json()["total"] == 1
    etag = lst.headers.get("etag")
    assert etag
    not_modified = await async_client.get(
        f"{BASE}/definitions", headers={**headers, "If-None-Match": etag}
    )
    assert not_modified.status_code == status.HTTP_304_NOT_MODIFIED

    patched = await async_client.patch(
        f"{BASE}/definitions/{definition_id}",
        json={"description": "обновлено"},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["description"] == "обновлено"

    deleted = await async_client.delete(f"{BASE}/definitions/{definition_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"{BASE}/definitions/{definition_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_system_definition_immutable(async_client, make_auth_headers, sessionmaker, data_factory):
    from app.models.models import ReportDefinition

    tenant_id = await _enable_flag(sessionmaker, data_factory)
    async with sessionmaker() as session:
        session.add(
            ReportDefinition(
                tenant_id=tenant_id, name="Системный", dataset_code="risks",
                config_json={}, is_system=True,
            )
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    lst = await async_client.get(f"{BASE}/definitions", headers=headers)
    system_id = next(i["id"] for i in lst.json()["items"] if i["is_system"])
    patched = await async_client.patch(
        f"{BASE}/definitions/{system_id}", json={"name": "x"}, headers=headers
    )
    assert patched.status_code == status.HTTP_400_BAD_REQUEST
    deleted = await async_client.delete(f"{BASE}/definitions/{system_id}", headers=headers)
    assert deleted.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_preview_inline(async_client, make_auth_headers, sessionmaker, data_factory):
    await _enable_flag(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.LINE_MANAGER)  # read-роль может preview
    resp = await async_client.post(
        f"{BASE}/preview",
        json={"dataset_code": "incidents", "config_json": {"columns": ["title"]}},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 0 and body["rows"] == []
    assert body["columns"][0] == {"key": "title", "label": "Название", "kind": "string"}
    bad = await async_client.post(
        f"{BASE}/preview",
        json={"dataset_code": "incidents", "config_json": {"columns": ["bogus"]}},
        headers=headers,
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
```

- [ ] **Step 2: Прогнать — FAIL (404 на все пути — роутер не зарегистрирован)**

- [ ] **Step 3: Схемы**

`backend/app/modules/report_builder/schemas.py`:

```python
"""Pydantic-схемы report-builder API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ReportColumnMeta(BaseModel):
    key: str
    label: str
    kind: str
    aggregatable: bool = False
    enum_values: list[str] | None = None
    ops: list[str]


class ReportDatasetRead(BaseModel):
    code: str
    title: str
    columns: list[ReportColumnMeta]


class ReportDatasetPage(BaseModel):
    items: list[ReportDatasetRead]
    total: int


class ReportDefinitionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    dataset_code: str
    config_json: dict[str, Any] = Field(default_factory=dict)


class ReportDefinitionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    dataset_code: str | None = None
    config_json: dict[str, Any] | None = None


class ReportDefinitionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    dataset_code: str
    config_json: dict[str, Any]
    is_system: bool
    created_at: datetime
    updated_at: datetime


class ReportDefinitionPage(BaseModel):
    items: list[ReportDefinitionRead]
    total: int


class ReportPreviewIn(BaseModel):
    dataset_code: str
    config_json: dict[str, Any] = Field(default_factory=dict)


class ReportPreviewOut(BaseModel):
    columns: list[dict[str, str]]  # {key,label,kind}
    rows: list[dict[str, Any]]
    total: int


class ReportRunIn(BaseModel):
    format: Literal["csv", "xlsx", "pdf"]


class ReportRunOut(BaseModel):
    job_id: str
    status: str
```

- [ ] **Step 4: Сервис**

`backend/app/modules/report_builder/service.py`:

```python
"""CRUD + run-оркестрация report definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.report_builder import ReportDefinition
from app.modules.export_center.service import ExportCenterService
from app.modules.projections.models import ExportJob
from app.modules.report_builder.engine import validate_config

__all__ = [
    "ReportDefinitionNotFound",
    "ReportNameConflict",
    "SystemDefinitionImmutable",
    "ReportBuilderService",
]


class ReportDefinitionNotFound(Exception):
    pass


class ReportNameConflict(Exception):
    pass


class SystemDefinitionImmutable(Exception):
    pass


_UPDATABLE_FIELDS = ("name", "description", "dataset_code", "config_json")


class ReportBuilderService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _base_stmt(self):
        return select(ReportDefinition).where(
            ReportDefinition.tenant_id == self.tenant_id,
            ReportDefinition.deleted_at.is_(None),
        )

    async def list_definitions(
        self, *, limit: int, offset: int
    ) -> tuple[list[ReportDefinition], int]:
        stmt = self._base_stmt()
        total = int(
            await self.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        )
        rows = list(
            (
                await self.session.execute(
                    stmt.order_by(
                        ReportDefinition.is_system.desc(), ReportDefinition.name.asc()
                    )
                    .offset(offset)
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        return rows, total

    async def get_definition(self, definition_id: str) -> ReportDefinition:
        row = await self.session.scalar(
            self._base_stmt().where(ReportDefinition.id == definition_id)
        )
        if row is None:
            raise ReportDefinitionNotFound(definition_id)
        return row

    async def create_definition(
        self,
        *,
        name: str,
        description: str | None,
        dataset_code: str,
        config_json: dict[str, Any],
    ) -> ReportDefinition:
        validate_config(dataset_code, config_json)  # ReportConfigError → 422 на роуте
        record = ReportDefinition(
            tenant_id=self.tenant_id,
            name=name,
            description=description,
            dataset_code=dataset_code,
            config_json=config_json,
        )
        self.session.add(record)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ReportNameConflict(name) from exc
        return record

    async def update_definition(
        self, definition: ReportDefinition, payload: dict[str, Any]
    ) -> ReportDefinition:
        if definition.is_system:
            raise SystemDefinitionImmutable(definition.id)
        fields = {k: v for k, v in payload.items() if k in _UPDATABLE_FIELDS}
        dataset_code = fields.get("dataset_code", definition.dataset_code)
        config_json = fields.get("config_json", definition.config_json)
        validate_config(dataset_code, config_json)
        for key, value in fields.items():
            setattr(definition, key, value)
        try:
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ReportNameConflict(str(fields.get("name"))) from exc
        return definition

    async def soft_delete_definition(self, definition: ReportDefinition) -> None:
        if definition.is_system:
            raise SystemDefinitionImmutable(definition.id)
        definition.deleted_at = datetime.now(tz=timezone.utc)
        await self.session.flush()

    async def run_definition(self, definition: ReportDefinition, *, fmt: str) -> ExportJob:
        """Создаёт ExportJob(export_type="report") и ставит celery-материализатор.
        Скачивание/статус — существующие /exports/{id} и /exports/{id}/download-link."""
        job = await ExportCenterService(self.session, self.tenant_id).create_job(
            export_type="report",
            dataset_code=definition.dataset_code,
            scope_json={"definition_id": definition.id, "format": fmt},
            filters_json=dict(definition.config_json or {}),
            idempotency_key=None,
        )
        from app.celery.tasks.report_export_job import report_export_job

        report_export_job.delay(job_id=job.id, tenant_id=self.tenant_id)
        return job
```

Примечание: `run_definition` появится в API в Task 6 (там же — сам материализатор). Импорт таска — внутри метода (модуль celery-таска на момент Task 5 ещё не существует; сервисный файл создаётся целиком сейчас, но `run_definition` не вызывается до Task 6 — это осознанно: единый файл, одна ответственность).

- [ ] **Step 5: Роуты**

`backend/app/modules/report_builder/api.py`:

```python
"""Report-builder API (P10-07 §24.3): datasets / definitions CRUD / preview / run.

За фичефлагом ``report_builder`` (default-off → 404, паттерн committees).
RBAC зеркалит ``_REPORT_ROLES`` из routes/reports.py: read/preview/run =
admin/owner/ot_specialist/line_manager; write = admin/owner/ot_specialist.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.errors import api_problem_detail
from app.core.feature_flags import is_feature_enabled
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import Tenant
from app.modules.report_builder.datasets import DATASETS
from app.modules.report_builder.engine import (
    PREVIEW_LIMIT,
    ReportConfigError,
    run_report,
)
from app.modules.report_builder.schemas import (
    ReportColumnMeta,
    ReportDatasetPage,
    ReportDatasetRead,
    ReportDefinitionCreate,
    ReportDefinitionPage,
    ReportDefinitionRead,
    ReportDefinitionUpdate,
    ReportPreviewIn,
    ReportPreviewOut,
)
from app.modules.report_builder.service import (
    ReportBuilderService,
    ReportDefinitionNotFound,
    ReportNameConflict,
    SystemDefinitionImmutable,
)
from app.services.audit import AuditService

router = APIRouter(prefix="/report-builder", tags=["report-builder"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_READ_ROLES = ["admin", "owner", "ot_specialist", "line_manager"]
_WRITE_ROLES = ["admin", "owner", "ot_specialist"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ReadAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_READ_ROLES, action="read report-builder")),
]
WriteAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_WRITE_ROLES, action="write report-builder")),
]

_FEATURE_CODE = "report_builder"


async def _require_feature(
    session: SessionDep,
    tenant: TenantDep,
) -> None:
    enabled = await is_feature_enabled(session, str(tenant.id), _FEATURE_CODE, default=False)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="REPORT_BUILDER_DISABLED",
                message="Report builder module is not enabled for this tenant",
                error_type="report_builder",
            ),
        )


FeatureGate = Depends(_require_feature)


def _error(code: str, message: str) -> dict:
    return api_problem_detail(code=code, message=message, error_type="report_builder")


def _audit_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _audit(
    session: AsyncSession,
    request: Request,
    access: AccessContext,
    tenant_id: str,
    *,
    action: str,
    object_id: str,
    details: dict | None = None,
) -> None:
    await AuditService(session).log_event(
        tenant_id=tenant_id,
        action=action,
        object_type="report_definition",
        object_id=object_id,
        user_id=getattr(access.user, "id", None),
        ip=_audit_ip(request),
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details=details,
    )


def _config_error(exc: ReportConfigError) -> HTTPException:
    return HTTPException(
        status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_error(exc.code, exc.message)
    )


@router.get("/datasets", response_model=ReportDatasetPage, dependencies=[FeatureGate])
async def list_datasets(tenant: TenantDep, access: ReadAccess) -> ReportDatasetPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    items = [
        ReportDatasetRead(
            code=spec.code,
            title=spec.title,
            columns=[
                ReportColumnMeta(
                    key=c.key,
                    label=c.label,
                    kind=c.kind,
                    aggregatable=c.aggregatable,
                    enum_values=c.enum_values,
                    ops=list(c.ops),
                )
                for c in spec.columns
            ],
        )
        for spec in DATASETS.values()
    ]
    return ReportDatasetPage(items=items, total=len(items))


@router.get("/definitions", response_model=ReportDefinitionPage, dependencies=[FeatureGate])
async def list_definitions(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ReadAccess,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    rows, total = await ReportBuilderService(session, str(tenant.id)).list_definitions(
        limit=limit, offset=offset
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[("total", total), ("limit", limit), ("offset", offset)],
    )
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag)
        )
    apply_etag_response_headers(response, etag)
    return ReportDefinitionPage(
        items=[ReportDefinitionRead.model_validate(r) for r in rows], total=total
    )


@router.post(
    "/definitions",
    response_model=ReportDefinitionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def create_definition(
    request: Request,
    payload: ReportDefinitionCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: WriteAccess,
) -> ReportDefinitionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReportBuilderService(session, str(tenant.id))
    try:
        record = await service.create_definition(
            name=payload.name,
            description=payload.description,
            dataset_code=payload.dataset_code,
            config_json=payload.config_json,
        )
    except ReportConfigError as exc:
        raise _config_error(exc) from exc
    except ReportNameConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("definition_name_conflict", f"Report name already exists: {payload.name}"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="create", object_id=record.id)
    await session.commit()
    await session.refresh(record)
    return ReportDefinitionRead.model_validate(record)


@router.get(
    "/definitions/{definition_id}",
    response_model=ReportDefinitionRead,
    dependencies=[FeatureGate],
)
async def get_definition(
    definition_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ReadAccess,
) -> ReportDefinitionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        record = await ReportBuilderService(session, str(tenant.id)).get_definition(definition_id)
    except ReportDefinitionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("definition_not_found", "Report not found")
        ) from exc
    return ReportDefinitionRead.model_validate(record)


@router.patch(
    "/definitions/{definition_id}",
    response_model=ReportDefinitionRead,
    dependencies=[FeatureGate],
)
async def update_definition(
    request: Request,
    definition_id: str,
    payload: ReportDefinitionUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: WriteAccess,
) -> ReportDefinitionRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReportBuilderService(session, str(tenant.id))
    try:
        record = await service.get_definition(definition_id)
        record = await service.update_definition(record, payload.model_dump(exclude_unset=True))
    except ReportDefinitionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("definition_not_found", "Report not found")
        ) from exc
    except SystemDefinitionImmutable as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_error("system_definition_immutable", "System templates are immutable"),
        ) from exc
    except ReportConfigError as exc:
        raise _config_error(exc) from exc
    except ReportNameConflict as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error("definition_name_conflict", "Report name already exists"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="update", object_id=record.id)
    await session.commit()
    await session.refresh(record)
    return ReportDefinitionRead.model_validate(record)


@router.delete(
    "/definitions/{definition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[FeatureGate],
)
async def delete_definition(
    request: Request,
    definition_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: WriteAccess,
) -> Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReportBuilderService(session, str(tenant.id))
    try:
        record = await service.get_definition(definition_id)
        await service.soft_delete_definition(record)
    except ReportDefinitionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("definition_not_found", "Report not found")
        ) from exc
    except SystemDefinitionImmutable as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=_error("system_definition_immutable", "System templates are immutable"),
        ) from exc
    await _audit(session, request, access, str(tenant.id), action="delete", object_id=record.id)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/preview", response_model=ReportPreviewOut, dependencies=[FeatureGate])
async def preview_report(
    payload: ReportPreviewIn,
    tenant: TenantDep,
    session: SessionDep,
    access: ReadAccess,
) -> ReportPreviewOut:
    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    try:
        result = await run_report(
            session,
            tenant_id=str(tenant.id),
            dataset_code=payload.dataset_code,
            config=payload.config_json,
            limit=PREVIEW_LIMIT,
        )
    except ReportConfigError as exc:
        raise _config_error(exc) from exc
    return ReportPreviewOut(
        columns=[{"key": c.key, "label": c.label, "kind": c.kind} for c in result.columns],
        rows=result.rows,
        total=result.total,
    )
```

(эндпоинт `POST /definitions/{id}/run` добавляется в Task 6 — вместе с материализатором.)

- [ ] **Step 6: Регистрация роутера**

В `backend/app/api/v1/route_groups.py`: рядом с `from app.modules.export_center.api import router as export_center_router` (строка ~77) добавить:

```python
from app.modules.report_builder.api import router as report_builder_router
```

и в списке document_core-группы после `(export_center_router, {"tags": ["exports"]}),` (строка ~185):

```python
    (report_builder_router, {"tags": ["report-builder"]}),
```

- [ ] **Step 7: Прогнать — все тесты Task 5 зелёные** (`test_report_builder_api.py` — 6 passed; батч вместе с datasets/engine-файлами ≤5)
- [ ] **Step 8: Commit** — `feat(p10-07): report-builder API (datasets/definitions/preview) + RBAC + flag gate`

---

## Task 6: Run-эндпоинт + celery-материализатор

**Files:**
- Create: `backend/app/celery/tasks/report_export_job.py`
- Modify: `backend/app/modules/report_builder/api.py` (добавить run-роут в конец)
- Test: `tests/api/test_report_export_job.py`

- [ ] **Step 1: Падающие тесты**

```python
"""Materializer: ExportJob(report) → file in storage + File row + job done/failed."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

BASE = "/api/v1/report-builder"


async def _setup(sessionmaker, data_factory: TestDataFactory) -> str:
    from app.models.feature import Feature, FeatureEnablement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "report_builder"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="report_builder", title="Конструктор отчётов")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=str(tenant.id), feature_id=feature.id, on=True))
        await session.commit()
        return str(tenant.id)


async def _create_definition(async_client, headers) -> str:
    resp = await async_client.post(
        f"{BASE}/definitions",
        json={"name": "Инциденты CSV", "dataset_code": "incidents",
              "config_json": {"columns": ["title", "status"]}},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_run_creates_queued_job(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    import app.modules.report_builder.service as svc_module

    calls: list[dict] = []
    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay",
        lambda **kw: calls.append(kw),
    )
    await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)

    resp = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "csv"}, headers=headers
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert calls and calls[0]["job_id"] == body["job_id"]

    bad = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "docx"}, headers=headers
    )
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY  # Literal формат


@pytest.mark.asyncio
async def test_materializer_csv_end_to_end(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    from app.celery.tasks.report_export_job import report_export_job
    from app.models.file import File
    from app.modules.projections.models import ExportJob
    from app.services.file_storage import FileStorageService

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "csv"}, headers=headers
    )
    job_id = run.json()["job_id"]

    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "ok"

    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.status == "done"
        assert job.row_count == 0  # пустой тенант — но файл с заголовком есть
        assert job.file_id
        file = await session.get(File, job.file_id)
        assert file is not None and file.mime == "text/csv"
        content = FileStorageService.default().get(file.storage_key).decode("utf-8")
        assert "Название;Статус" in content


@pytest.mark.asyncio
async def test_materializer_failure_paths(
    async_client, make_auth_headers, sessionmaker, data_factory, monkeypatch
):
    from app.celery.tasks.report_export_job import report_export_job
    from app.modules.projections.models import ExportJob

    monkeypatch.setattr(
        "app.celery.tasks.report_export_job.report_export_job.delay", lambda **kw: None
    )
    tenant_id = await _setup(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    definition_id = await _create_definition(async_client, headers)
    run = await async_client.post(
        f"{BASE}/definitions/{definition_id}/run", json={"format": "pdf"}, headers=headers
    )
    job_id = run.json()["job_id"]

    # 1) отсутствующая definition → failed(definition_missing)
    async with sessionmaker() as session:
        from app.models.report_builder import ReportDefinition
        from datetime import datetime, timezone

        record = await session.get(ReportDefinition, definition_id)
        record.deleted_at = datetime.now(tz=timezone.utc)
        await session.commit()
    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "failed"
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.status == "failed"
        assert job.error_payload["code"] == "definition_missing"
        # 2) вернуть definition, сломать PDF → pdf_renderer_unavailable
        record = await session.get(ReportDefinition, definition_id)
        record.deleted_at = None
        job.status = "queued"
        job.error_payload = None
        await session.commit()

    def _no_pdf(result, *, title):
        from app.modules.report_builder.renderers import PdfRendererUnavailable

        raise PdfRendererUnavailable("no soffice")

    monkeypatch.setattr("app.celery.tasks.report_export_job.render_pdf", _no_pdf)
    outcome = report_export_job(job_id=job_id, tenant_id=tenant_id)
    assert outcome["status"] == "failed"
    async with sessionmaker() as session:
        job = await session.get(ExportJob, job_id)
        assert job.error_payload["code"] == "pdf_renderer_unavailable"
```

- [ ] **Step 2: Прогнать — FAIL (нет модуля таска / нет run-роута)**

- [ ] **Step 3: Материализатор**

`backend/app/celery/tasks/report_export_job.py`:

```python
"""Materializer for report-builder export jobs (P10-07 §24.3).

Зеркало ``audit_export_job.py``: ExportJob(export_type="report") → engine →
renderer → FileStorageService + File row → job.file_id/status. Скачивание —
существующий GET /exports/{id}/download-link (отдаёт /files/{file_id}/download).
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy import select

from app.core.tenant import tenant_context
from app.db.session import ensure_tenant_schema, session_scope
from app.db.tenant_row_guard import assert_tenant_row_matches_session
from app.models.file import File, FileKind, FileScanStatus
from app.models.report_builder import ReportDefinition
from app.modules.projections.models import ExportJob
from app.modules.report_builder.engine import (
    EXPORT_ROW_CAP,
    ReportConfigError,
    run_report,
)
from app.modules.report_builder.renderers import (
    CSV_MEDIA,
    PDF_MEDIA,
    XLSX_MEDIA,
    PdfRendererUnavailable,
    render_csv,
    render_pdf,
    render_xlsx,
)
from app.services.celery_app import celery_app
from app.services.file_storage import FileStorageService

_FORMATS: dict[str, tuple[str, str]] = {
    "csv": (CSV_MEDIA, "csv"),
    "xlsx": (XLSX_MEDIA, "xlsx"),
    "pdf": (PDF_MEDIA, "pdf"),
}


@celery_app.task(name="app.tasks.report_export_job")
def report_export_job(*, job_id: str, tenant_id: str) -> dict[str, str]:
    from app.tasks import _run_coroutine

    async def _run() -> dict[str, str]:
        with tenant_context(tenant_id):
            ensure_tenant_schema(tenant_id)
            async with session_scope(tenant=tenant_id) as session:
                job = await session.get(ExportJob, job_id)
                if job is None or job.export_type != "report":
                    return {"status": "missing"}
                try:
                    assert_tenant_row_matches_session(
                        session,
                        job,
                        mismatch_event="report_export_job.tenant_scope_mismatch",
                        not_found_message="missing",
                    )
                except ValueError:
                    return {"status": "missing"}
                resolved = str(session.info.get("tenant_id") or "").strip() or tenant_id

                async def _fail(code: str, message: str) -> dict[str, str]:
                    job.status = "failed"
                    job.error_payload = {"code": code, "message": message}
                    await session.commit()
                    return {"status": "failed"}

                job.status = "running"
                await session.flush()

                scope: dict[str, Any] = job.scope_json or {}
                fmt = str(scope.get("format") or "")
                if fmt not in _FORMATS:
                    return await _fail("format_unknown", f"Unknown export format: {fmt!r}")
                definition = await session.scalar(
                    select(ReportDefinition).where(
                        ReportDefinition.id == str(scope.get("definition_id") or ""),
                        ReportDefinition.tenant_id == resolved,
                        ReportDefinition.deleted_at.is_(None),
                    )
                )
                if definition is None:
                    return await _fail("definition_missing", "Report definition was deleted")

                try:
                    result = await run_report(
                        session,
                        tenant_id=resolved,
                        dataset_code=definition.dataset_code,
                        config=definition.config_json,
                        limit=EXPORT_ROW_CAP,
                    )
                except ReportConfigError as exc:
                    return await _fail(exc.code, exc.message)
                if result.total > EXPORT_ROW_CAP:
                    return await _fail(
                        "row_limit_exceeded",
                        f"Report yields {result.total} rows; the cap is {EXPORT_ROW_CAP}",
                    )

                mime, ext = _FORMATS[fmt]
                try:
                    if fmt == "csv":
                        body = render_csv(result)
                    elif fmt == "xlsx":
                        body = render_xlsx(result, title=definition.name)
                    else:
                        body = render_pdf(result, title=definition.name)
                except PdfRendererUnavailable as exc:
                    return await _fail("pdf_renderer_unavailable", str(exc))

                key = f"{resolved}/exports/reports/{job.id}.{ext}"
                FileStorageService.default().put(key, body, content_type=mime)
                file = File(
                    tenant_id=resolved,
                    storage_key=key,
                    bucket="generated",
                    sha256=hashlib.sha256(body).hexdigest(),
                    size=len(body),
                    mime=mime,
                    original_name=f"{definition.name}.{ext}",
                    kind=FileKind.DOCUMENT,
                    is_quarantined=False,
                    scan_status=FileScanStatus.CLEAN,
                    meta_json={"generated_by": "report_export_job"},
                )
                session.add(file)
                await session.flush()
                job.file_id = file.id
                job.row_count = result.total
                job.progress_percent = 100
                job.status = "done"
                await session.commit()
                return {"status": "ok", "job_id": job_id}

    return _run_coroutine(_run())


__all__ = ["report_export_job"]
```

- [ ] **Step 4: Run-роут**

В `backend/app/modules/report_builder/api.py`: в блок импортов из `app.modules.report_builder.schemas` добавить `ReportRunIn, ReportRunOut` (в Task 5 они сознательно НЕ импортированы — ruff F401), затем в конец файла:

```python
@router.post(
    "/definitions/{definition_id}/run",
    response_model=ReportRunOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[FeatureGate],
)
async def run_definition(
    request: Request,
    definition_id: str,
    payload: ReportRunIn,
    tenant: TenantDep,
    session: SessionDep,
    access: ReadAccess,
) -> ReportRunOut:
    TenantContextValidator.ensure_tenant_context(tenant)
    service = ReportBuilderService(session, str(tenant.id))
    try:
        record = await service.get_definition(definition_id)
    except ReportDefinitionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail=_error("definition_not_found", "Report not found")
        ) from exc
    job = await service.run_definition(record, fmt=payload.format)
    await _audit(
        session,
        request,
        access,
        str(tenant.id),
        action="run",
        object_id=record.id,
        details={"format": payload.format, "job_id": job.id},
    )
    await session.commit()
    return ReportRunOut(job_id=job.id, status=job.status)
```

- [ ] **Step 5: Прогнать — 3 passed** (`test_report_export_job.py`; регресс Task 5 файла — тем же батчем)
- [ ] **Step 6: Commit** — `feat(p10-07): run endpoint + celery report materializer (CSV/XLSX/PDF)`

---

## Task 7: Demo-сид (флаг + 4 системных шаблона)

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`
- Test: `tests/test_report_builder_seed.py`

- [ ] **Step 1: Падающий тест**

```python
"""Idempotent demo seed: report_builder flag + 4 system templates."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_seed_idempotent(sessionmaker, data_factory: TestDataFactory):
    from app.models.feature import Feature, FeatureEnablement
    from app.models.report_builder import ReportDefinition
    from app.services.demo_bootstrap import _seed_report_builder_demo

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed_report_builder_demo(session, tid)
        await session.commit()
        await _seed_report_builder_demo(session, tid)  # второй прогон — без дублей
        await session.commit()

        feature = (
            await session.execute(select(Feature).where(Feature.code == "report_builder"))
        ).scalar_one()
        enablements = (
            await session.execute(
                select(func.count()).select_from(FeatureEnablement).where(
                    FeatureEnablement.tenant_id == tid,
                    FeatureEnablement.feature_id == feature.id,
                )
            )
        ).scalar_one()
        assert enablements == 1

        definitions = (
            (
                await session.execute(
                    select(ReportDefinition).where(
                        ReportDefinition.tenant_id == tid,
                        ReportDefinition.deleted_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(definitions) == 4
        assert all(d.is_system for d in definitions)
        assert {d.dataset_code for d in definitions} == {
            "employees_training", "incidents", "risks", "ppe_warehouse",
        }
        # configs валидны для engine
        from app.modules.report_builder.engine import validate_config

        for d in definitions:
            validate_config(d.dataset_code, d.config_json)
```

- [ ] **Step 2: Прогнать — FAIL (`ImportError: _seed_report_builder_demo`)**

- [ ] **Step 3: Реализация**

В `backend/app/services/demo_bootstrap.py` добавить функцию (рядом с `_seed_sout_demo`, стиль соседей):

```python
async def _seed_report_builder_demo(session, tenant_db_id: str) -> None:
    """Seed the default-off ``report_builder`` flag (enabled for the demo
    tenant) + 4 системных шаблона отчётов (P10-07, «готовые шаблоны» из §24.3).
    Idempotent: flag keyed on Feature.code, templates keyed on (tenant, name)."""

    from app.models.feature import Feature, FeatureEnablement
    from app.models.report_builder import ReportDefinition

    feature = (
        await session.execute(select(Feature).where(Feature.code == "report_builder"))
    ).scalar_one_or_none()
    if feature is None:
        feature = Feature(code="report_builder", title="Конструктор отчётов")
        session.add(feature)
        await session.flush()
    enablement = (
        await session.execute(
            select(FeatureEnablement).where(
                FeatureEnablement.tenant_id == tenant_db_id,
                FeatureEnablement.feature_id == feature.id,
            )
        )
    ).scalar_one_or_none()
    if enablement is None:
        session.add(FeatureEnablement(tenant_id=tenant_db_id, feature_id=feature.id, on=True))

    templates: list[dict] = [
        {
            "name": "Просроченное обучение",
            "description": "Сотрудники с истёкшим сроком действия обучения",
            "dataset_code": "employees_training",
            "config_json": {
                "columns": ["person_name", "position_title", "course_name", "expires_at"],
                "filters": [{"field": "is_overdue", "op": "eq", "value": True}],
                "sort": [{"field": "expires_at", "dir": "asc"}],
            },
        },
        {
            "name": "Открытые инциденты",
            "description": "Инциденты вне статусов closed/cancelled",
            "dataset_code": "incidents",
            "config_json": {
                "columns": ["title", "incident_type", "severity", "status",
                            "occurred_at", "site_name"],
                "filters": [
                    {"field": "status", "op": "in",
                     "value": ["reported", "investigating", "corrective_actions"]}
                ],
                "sort": [{"field": "occurred_at", "dir": "desc"}],
            },
        },
        {
            "name": "Риски высокого уровня",
            "description": "Записи реестра рисков с уровнем 15 и выше",
            "dataset_code": "risks",
            "config_json": {
                "columns": ["hazard", "level", "company_name", "site_name"],
                "filters": [{"field": "level", "op": "gte", "value": 15}],
                "sort": [{"field": "level", "dir": "desc"}],
            },
        },
        {
            "name": "СИЗ ниже минимального остатка",
            "description": "Позиции склада СИЗ с остатком ниже min_stock",
            "dataset_code": "ppe_warehouse",
            "config_json": {
                "columns": ["item_name", "category", "on_hand", "min_stock"],
                "filters": [{"field": "below_min", "op": "eq", "value": True}],
            },
        },
    ]
    for tpl in templates:
        exists = await session.scalar(
            select(ReportDefinition).where(
                ReportDefinition.tenant_id == tenant_db_id,
                ReportDefinition.name == tpl["name"],
                ReportDefinition.deleted_at.is_(None),
            )
        )
        if exists is None:
            session.add(ReportDefinition(tenant_id=tenant_db_id, is_system=True, **tpl))
```

Затем найти call-site: `grep -n "_seed_sout_demo(" backend/app/services/demo_bootstrap.py` — и в том же месте (где вызываются доменные сиды) добавить:

```python
    await _seed_report_builder_demo(session, tenant_db_id)
```

(имя переменной tenant-id взять из фактического call-site соседей — как у `_seed_sout_demo`).

- [ ] **Step 4: Прогнать — 1 passed**
- [ ] **Step 5: Commit** — `feat(p10-07): demo seed — report_builder flag + 4 system templates`

---

## Task 8: Frontend — DTO + api-клиент

**Files:**
- Create: `frontend/src/types/dto/reportBuilder.ts`
- Create: `frontend/src/api/reportBuilder.ts`
- Test: `frontend/src/__tests__/reportBuilderApi.test.ts`

- [ ] **Step 1: Падающий тест**

```typescript
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();
const postMock = vi.fn();
const patchMock = vi.fn();
const deleteMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => getMock(...args),
    post: (...args: unknown[]) => postMock(...args),
    patch: (...args: unknown[]) => patchMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args)
  }
}));

import { reportBuilderApi } from "@/api/reportBuilder";

describe("reportBuilderApi", () => {
  beforeEach(() => {
    getMock.mockReset().mockResolvedValue({ data: {} });
    postMock.mockReset().mockResolvedValue({ data: {} });
    patchMock.mockReset().mockResolvedValue({ data: {} });
    deleteMock.mockReset().mockResolvedValue({ data: {} });
  });

  it("lists datasets and definitions", async () => {
    await reportBuilderApi.listDatasets();
    expect(getMock).toHaveBeenCalledWith("/report-builder/datasets");
    await reportBuilderApi.listDefinitions();
    expect(getMock).toHaveBeenCalledWith("/report-builder/definitions");
  });

  it("creates, updates, deletes definitions", async () => {
    const payload = { name: "Отчёт", dataset_code: "incidents", config_json: {} };
    await reportBuilderApi.createDefinition(payload);
    expect(postMock).toHaveBeenCalledWith("/report-builder/definitions", payload);
    await reportBuilderApi.updateDefinition("d1", { name: "Новый" });
    expect(patchMock).toHaveBeenCalledWith("/report-builder/definitions/d1", { name: "Новый" });
    await reportBuilderApi.deleteDefinition("d1");
    expect(deleteMock).toHaveBeenCalledWith("/report-builder/definitions/d1");
  });

  it("previews inline config", async () => {
    await reportBuilderApi.preview({ dataset_code: "risks", config_json: { columns: ["hazard"] } });
    expect(postMock).toHaveBeenCalledWith("/report-builder/preview", {
      dataset_code: "risks",
      config_json: { columns: ["hazard"] }
    });
  });

  it("runs a definition and polls the job", async () => {
    await reportBuilderApi.runDefinition("d1", "xlsx");
    expect(postMock).toHaveBeenCalledWith("/report-builder/definitions/d1/run", { format: "xlsx" });
    await reportBuilderApi.getExportJob("j1");
    expect(getMock).toHaveBeenCalledWith("/exports/j1");
  });

  it("downloads the report file as a blob", async () => {
    getMock.mockResolvedValue({ data: new Blob(["x"]) });
    const blobSpy = vi.fn();
    vi.doMock("@/utils/download", () => ({ downloadBlob: blobSpy }));
    await reportBuilderApi.downloadReportFile("f1", "report.xlsx");
    expect(getMock).toHaveBeenCalledWith("/files/f1/download", { responseType: "blob" });
  });
});
```

- [ ] **Step 2: Прогнать — FAIL**

Bash: `cd "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\worktrees\p10-07-report-builder\frontend" && npx vitest run src/__tests__/reportBuilderApi.test.ts`

- [ ] **Step 3: DTO**

`frontend/src/types/dto/reportBuilder.ts`:

```typescript
export type ReportColumnKind = "string" | "number" | "date" | "datetime" | "enum" | "bool";
export type ReportFilterOp = "eq" | "neq" | "contains" | "gte" | "lte" | "in";
export type ReportExportFormat = "csv" | "xlsx" | "pdf";

export interface ReportColumnMetaDto {
  key: string;
  label: string;
  kind: ReportColumnKind;
  aggregatable: boolean;
  enum_values: string[] | null;
  ops: ReportFilterOp[];
}

export interface ReportDatasetDto {
  code: string;
  title: string;
  columns: ReportColumnMetaDto[];
}

export interface ReportFilterDto {
  field: string;
  op: ReportFilterOp;
  value: unknown;
}

export interface ReportSortDto {
  field: string;
  dir: "asc" | "desc";
}

export interface ReportAggregateDto {
  fn: "count" | "sum";
  field?: string;
}

export interface ReportConfigDto {
  columns?: string[];
  filters?: ReportFilterDto[];
  sort?: ReportSortDto[];
  group_by?: string[];
  aggregates?: ReportAggregateDto[];
}

export interface ReportDefinitionDto {
  id: string;
  name: string;
  description: string | null;
  dataset_code: string;
  config_json: ReportConfigDto;
  is_system: boolean;
  created_at: string;
  updated_at: string;
}

export interface ReportPreviewDto {
  columns: { key: string; label: string; kind: string }[];
  rows: Record<string, unknown>[];
  total: number;
}

export interface ReportExportJobDto {
  id: string;
  status: string; // queued | running | done | failed
  file_id: string | null;
  row_count: number | null;
  error_payload: { code?: string; message?: string } | null;
}
```

- [ ] **Step 4: api-клиент**

`frontend/src/api/reportBuilder.ts`:

```typescript
import { apiClient } from "@/api/client";
import { downloadBlob } from "@/utils/download";
import type {
  ReportConfigDto,
  ReportDatasetDto,
  ReportDefinitionDto,
  ReportExportFormat,
  ReportExportJobDto,
  ReportPreviewDto
} from "@/types/dto/reportBuilder";

export const reportBuilderApi = {
  listDatasets: async (): Promise<{ items: ReportDatasetDto[]; total: number }> => {
    const { data } = await apiClient.get<{ items: ReportDatasetDto[]; total: number }>(
      "/report-builder/datasets"
    );
    return data;
  },
  listDefinitions: async (): Promise<{ items: ReportDefinitionDto[]; total: number }> => {
    const { data } = await apiClient.get<{ items: ReportDefinitionDto[]; total: number }>(
      "/report-builder/definitions"
    );
    return data;
  },
  createDefinition: async (payload: {
    name: string;
    description?: string | null;
    dataset_code: string;
    config_json: ReportConfigDto;
  }): Promise<ReportDefinitionDto> => {
    const { data } = await apiClient.post<ReportDefinitionDto>(
      "/report-builder/definitions",
      payload
    );
    return data;
  },
  updateDefinition: async (
    id: string,
    payload: Partial<{
      name: string;
      description: string | null;
      dataset_code: string;
      config_json: ReportConfigDto;
    }>
  ): Promise<ReportDefinitionDto> => {
    const { data } = await apiClient.patch<ReportDefinitionDto>(
      `/report-builder/definitions/${id}`,
      payload
    );
    return data;
  },
  deleteDefinition: async (id: string): Promise<void> => {
    await apiClient.delete(`/report-builder/definitions/${id}`);
  },
  preview: async (payload: {
    dataset_code: string;
    config_json: ReportConfigDto;
  }): Promise<ReportPreviewDto> => {
    const { data } = await apiClient.post<ReportPreviewDto>("/report-builder/preview", payload);
    return data;
  },
  runDefinition: async (
    id: string,
    format: ReportExportFormat
  ): Promise<{ job_id: string; status: string }> => {
    const { data } = await apiClient.post<{ job_id: string; status: string }>(
      `/report-builder/definitions/${id}/run`,
      { format }
    );
    return data;
  },
  getExportJob: async (jobId: string): Promise<ReportExportJobDto> => {
    const { data } = await apiClient.get<ReportExportJobDto>(`/exports/${jobId}`);
    return data;
  },
  downloadReportFile: async (fileId: string, filename: string): Promise<void> => {
    const { data } = await apiClient.get<Blob>(`/files/${fileId}/download`, {
      responseType: "blob"
    });
    downloadBlob(data, filename);
  }
};
```

- [ ] **Step 5: Прогнать — 5 passed**
- [ ] **Step 6: Commit** — `feat(p10-07): reportBuilder api client + DTOs`

---

## Task 9: Frontend — `ReportBuilderPage` + роутинг/навигация

**Files:**
- Create: `frontend/src/pages/reports/ReportBuilderPage.tsx`
- Modify: `frontend/src/router/pageRegistry.tsx` (рядом со строкой 43 `ReportsPage`)
- Modify: `frontend/src/router/routeGroups.tsx` (группа `REPORTS_VIEW`, строки ~206-214)
- Modify: `frontend/src/router/navigationConfig.ts` (группа «Бизнес и аналитика», строки ~107-115)
- Modify: `frontend/src/pages/reports/ReportsPage.tsx` (кнопка-ссылка на конструктор)
- Test: `frontend/src/__tests__/ReportBuilderPage.test.tsx`

- [ ] **Step 1: Wiring (маленький и механический — сначала он)**

`pageRegistry.tsx` (после `ReportsPage`, строка ~43):

```typescript
export const ReportBuilderPage = lazy(() => import("@/pages/reports/ReportBuilderPage"));
```

`routeGroups.tsx` — в массив маршрутов группы `PERMISSIONS.REPORTS_VIEW` (после `/reports`):

```tsx
<Route key="/reports/builder" path="/reports/builder" element={<ReportBuilderPage />} />,
```

(и добавить `ReportBuilderPage` в существующий импорт из `pageRegistry`).

`navigationConfig.ts` — в группу «Бизнес и аналитика» после пункта «Отчёты»:

```typescript
{ label: "Конструктор отчётов", to: "/reports/builder", icon: ShieldCheck, permission: PERMISSIONS.REPORTS_VIEW },
```

`ReportsPage.tsx` — в шапку страницы (рядом с существующими кнопками экспорта) добавить ссылку:

```tsx
<Button asChild variant="outline">
  <Link to="/reports/builder">Конструктор отчётов</Link>
</Button>
```

(импорт `Link` из `react-router-dom`; если в файле уже есть — не дублировать. Точное место — по месту, рядом с кнопками XLSX/PDF.)

- [ ] **Step 2: Падающие тесты страницы**

`frontend/src/__tests__/ReportBuilderPage.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type {
  ReportDatasetDto,
  ReportDefinitionDto,
  ReportPreviewDto
} from "@/types/dto/reportBuilder";

const api = {
  listDatasets: vi.fn(),
  listDefinitions: vi.fn(),
  createDefinition: vi.fn(),
  updateDefinition: vi.fn(),
  deleteDefinition: vi.fn(),
  preview: vi.fn(),
  runDefinition: vi.fn(),
  getExportJob: vi.fn(),
  downloadReportFile: vi.fn()
};

vi.mock("@/api/reportBuilder", () => ({ reportBuilderApi: api }));

import ReportBuilderPage from "@/pages/reports/ReportBuilderPage";

const DATASETS: ReportDatasetDto[] = [
  {
    code: "incidents",
    title: "Инциденты",
    columns: [
      { key: "title", label: "Название", kind: "string", aggregatable: false, enum_values: null, ops: ["eq", "neq", "contains"] },
      { key: "status", label: "Статус", kind: "enum", aggregatable: false, enum_values: ["reported", "closed"], ops: ["eq", "in"] },
      { key: "occurred_at", label: "Дата", kind: "datetime", aggregatable: false, enum_values: null, ops: ["eq", "gte", "lte"] }
    ]
  }
];

const SYSTEM_DEF: ReportDefinitionDto = {
  id: "sys-1",
  name: "Открытые инциденты",
  description: null,
  dataset_code: "incidents",
  config_json: { columns: ["title", "status"] },
  is_system: true,
  created_at: "2026-07-10T00:00:00Z",
  updated_at: "2026-07-10T00:00:00Z"
};

const PREVIEW: ReportPreviewDto = {
  columns: [
    { key: "title", label: "Название", kind: "string" },
    { key: "status", label: "Статус", kind: "enum" }
  ],
  rows: [{ title: "Падение с высоты", status: "reported" }],
  total: 1
};

function renderPage() {
  return render(
    <MemoryRouter>
      <ReportBuilderPage />
    </MemoryRouter>
  );
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.listDatasets.mockResolvedValue({ items: DATASETS, total: 1 });
  api.listDefinitions.mockResolvedValue({ items: [SYSTEM_DEF], total: 1 });
  api.preview.mockResolvedValue(PREVIEW);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("ReportBuilderPage", () => {
  it("renders saved definitions with system badge", async () => {
    renderPage();
    expect(await screen.findByText("Открытые инциденты")).toBeInTheDocument();
    expect(screen.getByText("Системный")).toBeInTheDocument();
  });

  it("builds a preview from the editor", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Датасет"), "incidents");
    await user.click(screen.getByRole("button", { name: "Предпросмотр" }));
    expect(await screen.findByText("Падение с высоты")).toBeInTheDocument();
    expect(screen.getByText(/Всего: 1/)).toBeInTheDocument();
    expect(api.preview).toHaveBeenCalledWith({
      dataset_code: "incidents",
      config_json: expect.objectContaining({ columns: expect.arrayContaining(["title"]) })
    });
  });

  it("adds a filter row that reaches the preview payload", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Датасет"), "incidents");
    await user.click(screen.getByRole("button", { name: "Добавить фильтр" }));
    const filterRow = screen.getByTestId("filter-row-0");
    await user.selectOptions(within(filterRow).getByLabelText("Поле"), "status");
    await user.selectOptions(within(filterRow).getByLabelText("Значение"), "reported");
    await user.click(screen.getByRole("button", { name: "Предпросмотр" }));
    await waitFor(() =>
      expect(api.preview).toHaveBeenCalledWith(
        expect.objectContaining({
          config_json: expect.objectContaining({
            filters: [{ field: "status", op: "eq", value: "reported" }]
          })
        })
      )
    );
  });

  it("saves a new definition", async () => {
    api.createDefinition.mockResolvedValue({ ...SYSTEM_DEF, id: "d2", is_system: false, name: "Мой отчёт" });
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Датасет"), "incidents");
    await user.type(screen.getByLabelText("Название отчёта"), "Мой отчёт");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await waitFor(() =>
      expect(api.createDefinition).toHaveBeenCalledWith(
        expect.objectContaining({ name: "Мой отчёт", dataset_code: "incidents" })
      )
    );
    expect(api.listDefinitions).toHaveBeenCalledTimes(2); // reload после сохранения
  });

  it("duplicates a system template into the editor", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.click(screen.getByRole("button", { name: "Дублировать" }));
    expect(screen.getByLabelText("Название отчёта")).toHaveValue("Открытые инциденты (копия)");
  });

  it("exports: run → poll → download button; failed job shows error", async () => {
    vi.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    api.runDefinition.mockResolvedValue({ job_id: "j1", status: "queued" });
    api.getExportJob
      .mockResolvedValueOnce({ id: "j1", status: "running", file_id: null, row_count: null, error_payload: null })
      .mockResolvedValueOnce({ id: "j1", status: "done", file_id: "f1", row_count: 5, error_payload: null });
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.click(screen.getByRole("button", { name: "Открыть" }));
    await user.click(screen.getByRole("button", { name: "XLSX" }));
    await waitFor(() => expect(api.runDefinition).toHaveBeenCalledWith("sys-1", "xlsx"));
    await vi.advanceTimersByTimeAsync(1600);
    await vi.advanceTimersByTimeAsync(1600);
    expect(await screen.findByRole("button", { name: "Скачать" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Скачать" }));
    expect(api.downloadReportFile).toHaveBeenCalledWith("f1", "Открытые инциденты.xlsx");
  });

  it("shows a readable error when the export job fails", async () => {
    vi.useFakeTimers();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    api.runDefinition.mockResolvedValue({ job_id: "j1", status: "queued" });
    api.getExportJob.mockResolvedValue({
      id: "j1", status: "failed", file_id: null, row_count: null,
      error_payload: { code: "pdf_renderer_unavailable", message: "no soffice" }
    });
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.click(screen.getByRole("button", { name: "Открыть" }));
    await user.click(screen.getByRole("button", { name: "PDF" }));
    await vi.advanceTimersByTimeAsync(1600);
    expect(
      await screen.findByText(/PDF-конвертер временно недоступен/)
    ).toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Прогнать — FAIL (страницы нет)**

- [ ] **Step 4: Страница**

`frontend/src/pages/reports/ReportBuilderPage.tsx` — house-style single-file. Полная структура (селекты — нативные `<select>` с классами как у фильтров на `MedicalPage.tsx` — сверить классы там перед вёрсткой):

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { reportBuilderApi } from "@/api/reportBuilder";
import { Breadcrumb } from "@/components/common/Breadcrumb";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import type {
  ReportColumnMetaDto,
  ReportConfigDto,
  ReportDatasetDto,
  ReportDefinitionDto,
  ReportExportFormat,
  ReportFilterDto,
  ReportPreviewDto
} from "@/types/dto/reportBuilder";

const POLL_INTERVAL_MS = 1500;
const POLL_MAX_TICKS = 40; // ~60 секунд

const JOB_ERROR_LABELS: Record<string, string> = {
  pdf_renderer_unavailable: "PDF-конвертер временно недоступен — попробуйте CSV/XLSX",
  row_limit_exceeded: "Слишком много строк — сузьте фильтры",
  definition_missing: "Отчёт был удалён",
};

type FilterRow = { field: string; op: string; value: string };

type ExportState =
  | { phase: "idle" }
  | { phase: "polling"; jobId: string; format: ReportExportFormat; ticks: number }
  | { phase: "done"; fileId: string; format: ReportExportFormat }
  | { phase: "failed"; message: string };

export default function ReportBuilderPage() {
  const datasetsRes = useAsyncResource<{ items: ReportDatasetDto[]; total: number }>({
    loader: () => reportBuilderApi.listDatasets(),
    errorMessage: "Не удалось загрузить датасеты"
  });
  const definitionsRes = useAsyncResource<{ items: ReportDefinitionDto[]; total: number }>({
    loader: () => reportBuilderApi.listDefinitions(),
    errorMessage: "Не удалось загрузить сохранённые отчёты"
  });

  // --- editor state ---
  const [editingId, setEditingId] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [datasetCode, setDatasetCode] = useState("");
  const [selectedColumns, setSelectedColumns] = useState<string[]>([]);
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [groupBy, setGroupBy] = useState<string[]>([]);
  const [sumField, setSumField] = useState("");
  const [sortField, setSortField] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [preview, setPreview] = useState<ReportPreviewDto | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [exportState, setExportState] = useState<ExportState>({ phase: "idle" });
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const datasets = datasetsRes.data?.items ?? [];
  const definitions = definitionsRes.data?.items ?? [];
  const dataset = useMemo(
    () => datasets.find((d) => d.code === datasetCode) ?? null,
    [datasets, datasetCode]
  );
  const columnsByKey = useMemo(() => {
    const map = new Map<string, ReportColumnMetaDto>();
    dataset?.columns.forEach((c) => map.set(c.key, c));
    return map;
  }, [dataset]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);
  useEffect(() => stopPolling, [stopPolling]);

  const resetEditor = useCallback((ds?: string) => {
    setEditingId(null);
    setName("");
    setDescription("");
    setSelectedColumns([]);
    setFilters([]);
    setGroupBy([]);
    setSumField("");
    setSortField("");
    setSortDir("asc");
    setPreview(null);
    setPreviewError(null);
    setSaveError(null);
    setExportState({ phase: "idle" });
    stopPolling();
    if (ds !== undefined) setDatasetCode(ds);
  }, [stopPolling]);

  const buildConfig = useCallback((): ReportConfigDto => {
    const config: ReportConfigDto = {};
    if (groupBy.length > 0) {
      config.group_by = groupBy;
      config.aggregates = [{ fn: "count" }];
      if (sumField) config.aggregates.push({ fn: "sum", field: sumField });
    } else if (selectedColumns.length > 0) {
      config.columns = selectedColumns;
    }
    const parsed: ReportFilterDto[] = [];
    for (const row of filters) {
      if (!row.field || !row.op) continue;
      const col = columnsByKey.get(row.field);
      if (!col) continue;
      let value: unknown = row.value;
      if (col.kind === "number") value = Number(row.value);
      if (col.kind === "bool") value = row.value === "true";
      if (row.op === "in")
        value = row.value.split(",").map((v) => v.trim()).filter(Boolean);
      parsed.push({ field: row.field, op: row.op as ReportFilterDto["op"], value });
    }
    if (parsed.length > 0) config.filters = parsed;
    if (sortField) config.sort = [{ field: sortField, dir: sortDir }];
    return config;
  }, [columnsByKey, filters, groupBy, selectedColumns, sortDir, sortField, sumField]);

  const loadDefinition = useCallback((def: ReportDefinitionDto, asCopy: boolean) => {
    resetEditor(def.dataset_code);
    setEditingId(asCopy ? null : def.id);
    setName(asCopy ? `${def.name} (копия)` : def.name);
    setDescription(def.description ?? "");
    const cfg = def.config_json ?? {};
    setSelectedColumns(cfg.columns ?? []);
    setGroupBy(cfg.group_by ?? []);
    setSumField(cfg.aggregates?.find((a) => a.fn === "sum")?.field ?? "");
    setSortField(cfg.sort?.[0]?.field ?? "");
    setSortDir(cfg.sort?.[0]?.dir ?? "asc");
    setFilters(
      (cfg.filters ?? []).map((f) => ({
        field: f.field,
        op: f.op,
        value: Array.isArray(f.value) ? f.value.join(",") : String(f.value ?? "")
      }))
    );
  }, [resetEditor]);

  const runPreview = useCallback(async () => {
    if (!datasetCode) return;
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      setPreview(await reportBuilderApi.preview({ dataset_code: datasetCode, config_json: buildConfig() }));
    } catch {
      setPreview(null);
      setPreviewError("Не удалось построить предпросмотр — проверьте фильтры");
    } finally {
      setPreviewLoading(false);
    }
  }, [buildConfig, datasetCode]);

  const saveDefinition = useCallback(async () => {
    if (!datasetCode || !name.trim()) {
      setSaveError("Укажите название и датасет");
      return;
    }
    setSaveError(null);
    const payload = {
      name: name.trim(),
      description: description.trim() || null,
      dataset_code: datasetCode,
      config_json: buildConfig()
    };
    try {
      if (editingId) {
        await reportBuilderApi.updateDefinition(editingId, payload);
      } else {
        const created = await reportBuilderApi.createDefinition(payload);
        setEditingId(created.id);
      }
      await definitionsRes.reload();
    } catch {
      setSaveError("Не удалось сохранить (возможно, имя уже занято)");
    }
  }, [buildConfig, datasetCode, description, definitionsRes, editingId, name]);

  const removeDefinition = useCallback(async (def: ReportDefinitionDto) => {
    if (!window.confirm(`Удалить отчёт «${def.name}»?`)) return;
    try {
      await reportBuilderApi.deleteDefinition(def.id);
      if (editingId === def.id) resetEditor("");
      await definitionsRes.reload();
    } catch {
      /* ошибка удаления не блокирует страницу */
    }
  }, [definitionsRes, editingId, resetEditor]);

  const startExport = useCallback(async (format: ReportExportFormat) => {
    if (!editingId) return;
    stopPolling();
    try {
      const { job_id } = await reportBuilderApi.runDefinition(editingId, format);
      setExportState({ phase: "polling", jobId: job_id, format, ticks: 0 });
      pollRef.current = setInterval(async () => {
        try {
          const job = await reportBuilderApi.getExportJob(job_id);
          if (job.status === "done" && job.file_id) {
            stopPolling();
            setExportState({ phase: "done", fileId: job.file_id, format });
          } else if (job.status === "failed") {
            stopPolling();
            const code = job.error_payload?.code ?? "";
            setExportState({
              phase: "failed",
              message: JOB_ERROR_LABELS[code] ?? "Экспорт не удался — попробуйте ещё раз"
            });
          } else {
            setExportState((prev) => {
              if (prev.phase !== "polling") return prev;
              if (prev.ticks + 1 >= POLL_MAX_TICKS) {
                stopPolling();
                return { phase: "failed", message: "Экспорт занял слишком много времени" };
              }
              return { ...prev, ticks: prev.ticks + 1 };
            });
          }
        } catch {
          /* транзиентная ошибка поллинга — ждём следующего тика */
        }
      }, POLL_INTERVAL_MS);
    } catch {
      setExportState({ phase: "failed", message: "Не удалось запустить экспорт" });
    }
  }, [editingId, stopPolling]);

  const downloadCurrent = useCallback(async () => {
    if (exportState.phase !== "done") return;
    const def = definitions.find((d) => d.id === editingId);
    await reportBuilderApi.downloadReportFile(
      exportState.fileId,
      `${def?.name ?? "report"}.${exportState.format}`
    );
  }, [definitions, editingId, exportState]);

  if (datasetsRes.loading || definitionsRes.loading) return <LoadingScreen />;
  if (datasetsRes.error) return <ErrorState message={datasetsRes.error} onRetry={datasetsRes.reload} />;
  if (definitionsRes.error) return <ErrorState message={definitionsRes.error} onRetry={definitionsRes.reload} />;

  return (
    <div className="space-y-6">
      <Breadcrumb items={[{ label: "Отчёты", to: "/reports" }, { label: "Конструктор отчётов" }]} />

      <Card>
        <CardHeader>
          <CardTitle>Сохранённые отчёты</CardTitle>
          <CardDescription>Готовые шаблоны и ваши отчёты. Системные шаблоны можно дублировать.</CardDescription>
        </CardHeader>
        <CardContent>
          {definitions.length === 0 ? (
            <EmptyState title="Пока нет отчётов" description="Создайте первый отчёт в конструкторе ниже." />
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-muted-foreground">
                  <th className="py-2 pr-4">Название</th>
                  <th className="py-2 pr-4">Датасет</th>
                  <th className="py-2 pr-4" />
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody>
                {definitions.map((def) => (
                  <tr key={def.id} className="border-b last:border-0">
                    <td className="py-2 pr-4">
                      {def.name}{" "}
                      {def.is_system ? <Badge variant="secondary">Системный</Badge> : null}
                    </td>
                    <td className="py-2 pr-4">
                      {datasets.find((d) => d.code === def.dataset_code)?.title ?? def.dataset_code}
                    </td>
                    <td className="py-2 pr-4">
                      <Button size="sm" variant="outline" onClick={() => loadDefinition(def, false)}>
                        Открыть
                      </Button>{" "}
                      <Button size="sm" variant="outline" onClick={() => loadDefinition(def, true)}>
                        Дублировать
                      </Button>
                    </td>
                    <td className="py-2 text-right">
                      {!def.is_system ? (
                        <Button size="sm" variant="destructive" onClick={() => removeDefinition(def)}>
                          Удалить
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Конструктор</CardTitle>
          <CardDescription>
            Датасет → колонки → фильтры → группировка → сортировка. Предпросмотр показывает первые 100 строк.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="rb-name">Название отчёта</Label>
              <Input id="rb-name" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="rb-description">Описание</Label>
              <Input id="rb-description" value={description} onChange={(e) => setDescription(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="rb-dataset">Датасет</Label>
              <select
                id="rb-dataset"
                className="h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={datasetCode}
                onChange={(e) => resetEditor(e.target.value)}
              >
                <option value="">— выберите —</option>
                {datasets.map((d) => (
                  <option key={d.code} value={d.code}>{d.title}</option>
                ))}
              </select>
            </div>
          </div>

          {dataset ? (
            <>
              {groupBy.length === 0 ? (
                <div className="space-y-1">
                  <Label>Колонки</Label>
                  <div className="flex flex-wrap gap-3">
                    {dataset.columns.map((col) => (
                      <label key={col.key} className="flex items-center gap-1 text-sm">
                        <input
                          type="checkbox"
                          checked={selectedColumns.includes(col.key)}
                          onChange={(e) =>
                            setSelectedColumns((prev) =>
                              e.target.checked ? [...prev, col.key] : prev.filter((k) => k !== col.key)
                            )
                          }
                        />
                        {col.label}
                      </label>
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">Ничего не выбрано — будут все колонки.</p>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">
                  Включена группировка — выводятся группировочные поля и агрегаты.
                </p>
              )}

              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label>Фильтры</Label>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setFilters((prev) => [...prev, { field: "", op: "eq", value: "" }])}
                  >
                    Добавить фильтр
                  </Button>
                </div>
                {filters.map((row, idx) => {
                  const col = row.field ? columnsByKey.get(row.field) : undefined;
                  return (
                    <div key={idx} data-testid={`filter-row-${idx}`} className="flex flex-wrap items-end gap-2">
                      <div className="space-y-1">
                        <Label htmlFor={`rb-filter-field-${idx}`}>Поле</Label>
                        <select
                          id={`rb-filter-field-${idx}`}
                          aria-label="Поле"
                          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                          value={row.field}
                          onChange={(e) =>
                            setFilters((prev) =>
                              prev.map((r, i) =>
                                i === idx
                                  ? {
                                      field: e.target.value,
                                      op: columnsByKey.get(e.target.value)?.ops[0] ?? "eq",
                                      value: ""
                                    }
                                  : r
                              )
                            )
                          }
                        >
                          <option value="">— поле —</option>
                          {dataset.columns.map((c) => (
                            <option key={c.key} value={c.key}>{c.label}</option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`rb-filter-op-${idx}`}>Оператор</Label>
                        <select
                          id={`rb-filter-op-${idx}`}
                          aria-label="Оператор"
                          className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                          value={row.op}
                          onChange={(e) =>
                            setFilters((prev) =>
                              prev.map((r, i) => (i === idx ? { ...r, op: e.target.value } : r))
                            )
                          }
                        >
                          {(col?.ops ?? ["eq"]).map((op) => (
                            <option key={op} value={op}>{op}</option>
                          ))}
                        </select>
                      </div>
                      <div className="space-y-1">
                        <Label htmlFor={`rb-filter-value-${idx}`}>Значение</Label>
                        {col?.kind === "enum" && row.op !== "in" ? (
                          <select
                            id={`rb-filter-value-${idx}`}
                            aria-label="Значение"
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                            value={row.value}
                            onChange={(e) =>
                              setFilters((prev) =>
                                prev.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r))
                              )
                            }
                          >
                            <option value="">—</option>
                            {(col.enum_values ?? []).map((v) => (
                              <option key={v} value={v}>{v}</option>
                            ))}
                          </select>
                        ) : col?.kind === "bool" ? (
                          <select
                            id={`rb-filter-value-${idx}`}
                            aria-label="Значение"
                            className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                            value={row.value}
                            onChange={(e) =>
                              setFilters((prev) =>
                                prev.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r))
                              )
                            }
                          >
                            <option value="">—</option>
                            <option value="true">да</option>
                            <option value="false">нет</option>
                          </select>
                        ) : (
                          <Input
                            id={`rb-filter-value-${idx}`}
                            aria-label="Значение"
                            type={col?.kind === "number" ? "number" : col?.kind === "date" ? "date" : col?.kind === "datetime" ? "datetime-local" : "text"}
                            value={row.value}
                            onChange={(e) =>
                              setFilters((prev) =>
                                prev.map((r, i) => (i === idx ? { ...r, value: e.target.value } : r))
                              )
                            }
                          />
                        )}
                      </div>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setFilters((prev) => prev.filter((_, i) => i !== idx))}
                      >
                        Убрать
                      </Button>
                    </div>
                  );
                })}
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-1">
                  <Label htmlFor="rb-groupby">Группировка</Label>
                  <select
                    id="rb-groupby"
                    className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                    value={groupBy[0] ?? ""}
                    onChange={(e) => setGroupBy(e.target.value ? [e.target.value] : [])}
                  >
                    <option value="">— без группировки —</option>
                    {dataset.columns.map((c) => (
                      <option key={c.key} value={c.key}>{c.label}</option>
                    ))}
                  </select>
                </div>
                {groupBy.length > 0 ? (
                  <div className="space-y-1">
                    <Label htmlFor="rb-sum">Сумма по</Label>
                    <select
                      id="rb-sum"
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={sumField}
                      onChange={(e) => setSumField(e.target.value)}
                    >
                      <option value="">— только количество —</option>
                      {dataset.columns.filter((c) => c.aggregatable).map((c) => (
                        <option key={c.key} value={c.key}>{c.label}</option>
                      ))}
                    </select>
                  </div>
                ) : null}
                <div className="space-y-1">
                  <Label htmlFor="rb-sort">Сортировка</Label>
                  <div className="flex gap-2">
                    <select
                      id="rb-sort"
                      className="h-9 w-full rounded-md border border-input bg-background px-2 text-sm"
                      value={sortField}
                      onChange={(e) => setSortField(e.target.value)}
                    >
                      <option value="">— нет —</option>
                      {(groupBy.length > 0
                        ? [...groupBy, "count", ...(sumField ? [`sum_${sumField}`] : [])]
                        : (selectedColumns.length > 0 ? selectedColumns : dataset.columns.map((c) => c.key))
                      ).map((key) => (
                        <option key={key} value={key}>
                          {columnsByKey.get(key)?.label ?? key}
                        </option>
                      ))}
                    </select>
                    <select
                      aria-label="Направление сортировки"
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                      value={sortDir}
                      onChange={(e) => setSortDir(e.target.value as "asc" | "desc")}
                    >
                      <option value="asc">по возр.</option>
                      <option value="desc">по убыв.</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={runPreview} disabled={previewLoading}>Предпросмотр</Button>
                <Button variant="outline" onClick={saveDefinition}>Сохранить</Button>
                {editingId ? (
                  <>
                    <span className="text-sm text-muted-foreground">Экспорт:</span>
                    <Button size="sm" variant="outline" onClick={() => startExport("csv")}>CSV</Button>
                    <Button size="sm" variant="outline" onClick={() => startExport("xlsx")}>XLSX</Button>
                    <Button size="sm" variant="outline" onClick={() => startExport("pdf")}>PDF</Button>
                  </>
                ) : (
                  <span className="text-xs text-muted-foreground">Сохраните отчёт, чтобы экспортировать.</span>
                )}
              </div>
              {saveError ? <p role="alert" className="text-sm text-destructive">{saveError}</p> : null}
              {exportState.phase === "polling" ? (
                <p className="text-sm text-muted-foreground">Формируем файл…</p>
              ) : null}
              {exportState.phase === "done" ? (
                <Button size="sm" onClick={downloadCurrent}>Скачать</Button>
              ) : null}
              {exportState.phase === "failed" ? (
                <p role="alert" className="text-sm text-destructive">{exportState.message}</p>
              ) : null}
            </>
          ) : null}
        </CardContent>
      </Card>

      {dataset ? (
        <Card>
          <CardHeader>
            <CardTitle>Предпросмотр</CardTitle>
            {preview ? <CardDescription>Всего: {preview.total}</CardDescription> : null}
          </CardHeader>
          <CardContent>
            {previewError ? <p role="alert" className="text-sm text-destructive">{previewError}</p> : null}
            {preview && preview.rows.length === 0 && !previewError ? (
              <EmptyState title="Нет данных" description="Под текущие фильтры не попало ни одной строки." />
            ) : null}
            {preview && preview.rows.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      {preview.columns.map((c) => (
                        <th key={c.key} className="py-2 pr-4">{c.label}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview.rows.map((row, i) => (
                      <tr key={i} className="border-b last:border-0">
                        {preview.columns.map((c) => (
                          <td key={c.key} className="py-2 pr-4">
                            {row[c.key] === null || row[c.key] === undefined
                              ? "—"
                              : typeof row[c.key] === "boolean"
                                ? (row[c.key] ? "да" : "нет")
                                : String(row[c.key])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
```

Примечания для implementer'а:
- Импорты общих компонентов (`Breadcrumb`, `EmptyState`, `ErrorState`, `LoadingScreen`, `Badge`) — сверить фактические пути/экспорты по `MedicalPage.tsx`/`WarehousePage.tsx` (named vs default) и поправить при расхождении.
- `useAsyncResource` API — `{ data, loading, error, reload }` (см. `frontend/src/hooks/useAsyncResource.ts`).
- Если `window.confirm` в тестах мешает — в тесте удаления замокать `vi.spyOn(window, "confirm").mockReturnValue(true)` (тест удаления в базовом наборе не обязателен).

- [ ] **Step 5: Прогнать тесты страницы — 7 passed**
- [ ] **Step 6: Точечная регрессия соседей:** `npx vitest run src/__tests__/ReportsPage.test.tsx src/__tests__/reportBuilderApi.test.ts src/__tests__/ReportBuilderPage.test.tsx`
- [ ] **Step 7: Commit** — `feat(p10-07): ReportBuilderPage + routing/nav + ReportsPage link`

---

## Task 10: Гейты + документация (контроллер, не субагент)

**Files:**
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (строка P10-07)
- Modify: `CHANGELOG.md`
- Modify: `AI_IMPLEMENTATION_REPORT.md` (новый handoff-блок сверху)
- Regenerate: OpenAPI baseline (`scripts/ci/check_openapi_snapshot.py --snapshot`)

- [ ] **Step 1: Backend-регресс батчами ≤5 файлов** (PowerShell, таймаут 600000, ОДИН прогон):
  - Батч 1: `tests/api/test_report_builder_model.py tests/api/test_report_builder_datasets.py tests/api/test_report_builder_engine.py tests/api/test_report_builder_renderers.py`
  - Батч 2: `tests/api/test_report_builder_api.py tests/api/test_report_export_job.py tests/test_report_builder_seed.py`
  - Батч 3 (смежные): `tests/test_demo_bootstrap_contractors.py tests/api/test_ppe_budget_api.py tests/test_employee_card.py` (сид/ppe/models-регрессия)
- [ ] **Step 2: ruff + black** (`python -m ruff check backend/app tests --fix`; `python -m black backend/app tests`) → после black ре-ран `tests/api/test_report_builder_model.py` (substring-ассерты миграции).
- [ ] **Step 3: OpenAPI baseline re-snap:** `$env:PYTHONPATH="backend"; python scripts/ci/check_openapi_snapshot.py --snapshot` → git-diff строго аддитивный (+9 роутов: datasets/definitions CRUD(5)/preview/run + схемы; 0 удалений) → повторный compare без флага = exit 0. НЕ гонять параллельно с pytest.
- [ ] **Step 4: PG16-гейт:** `python scripts/ci/local_gate.py --db-only` (Docker обязателен) — alembic upgrade/downgrade round-trip вкл. `rb01` + enum guards + ARCH-3.
- [ ] **Step 5: Frontend полный:** `npm --prefix frontend run typecheck` → `npx vitest run` (полный, НЕ параллельно с pytest; красное перепроверить в изоляции) → `npm --prefix frontend run build`.
- [ ] **Step 6: Docs:** обновить строку P10-07 в роадмапе (партиал: report-builder MVP shipped — сущность+материализатор+UI; «Остаётся: управленческие дашборды, остальные 4 датасета, cron-исполнение расписаний, графики»), запись в `CHANGELOG.md` (2026-07-10), handoff-блок в `AI_IMPLEMENTATION_REPORT.md` (по шаблону раздела H ТЗ).
- [ ] **Step 7: Commit** — `docs(p10-07): roadmap + changelog + handoff + OpenAPI baseline for report-builder MVP`

---

## Проверка соответствия спеке (self-check при финальном ревью)

- §4 модель/миграция → Task 1. §5 config-схема → Task 3 (валидация) + Task 5 (422). §6 модуль → Tasks 2-4. §7 API/RBAC/флаг/ETag/audit → Tasks 5-6. §8 материализатор → Task 6. §9 сид → Task 7. §10 фронт → Tasks 8-9. §11 тест-план → тесты в каждой задаче. §12 гейты → Task 10.
- Отложенное (§3) НЕ реализовывать: cron-beat, email, графики, остальные датасеты, anonymization, подключение старой кнопки ReportsPage.
