# P10-07 Управленческие дашборды (§24.2) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Управленческий аналитик-хаб `/analytics`: фильтры + KPI-карты + 6 графиков трендов (recharts) + breakdown по компаниям/объектам/подрядчикам; плюс RBAC-хардening analytics/export_center-роутеров и фикс дубль-регистрации operational_dashboard.

**Architecture:** Backend — ABAC-гейты на существующие роутеры + один новый вычисляемый эндпоинт `GET /analytics/dashboard/breakdown` (по одному SQL GROUP BY на метрику, сшивка в Python, без миграций/персистенса). Frontend — новая зависимость recharts + обёртка TrendLineChart + типизированный analyticsApi + страница ManagementDashboardPage за новым правом `ANALYTICS_VIEW`. Спека: `docs/superpowers/specs/2026-07-11-p10-07-management-dashboards-design.md`.

**Tech Stack:** FastAPI + SQLAlchemy async (без Alembic — миграций нет); React 18 + recharts + vitest.

**Операционка (ОБЯЗАТЕЛЬНО для каждого implementer'а):**
- Рабочая копия: `D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\worktrees\p10-07-mgmt-dashboards` (ветка `feat/p10-07-management-dashboards`). Пути ниже — относительно неё.
- Backend-тесты — ТОЛЬКО PowerShell-инструмент: `& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest <files> -q` из корня worktree. Таймаут 600000 мс. ОДИН прогон без ретраев (холодный импорт 2–3 мин). Git-Bash для pytest НЕ использовать (сегфолт). Батчи ≤5 файлов. Ориентир — `$LASTEXITCODE`.
- Frontend — Bash с АБСОЛЮТНЫМ cwd: `cd "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\worktrees\p10-07-mgmt-dashboards\frontend" && npx vitest run <files>`. `node_modules` уже установлены. Полный vitest НЕ гонять (контроллер).
- git-команды — `git -C "<абсолютный путь worktree>"` (PowerShell держит cwd между вызовами).
- Коммит после каждой задачи.

---

## Task 1: RBAC-хардening (analytics + export_center) + дедуп operational_dashboard

**Files:**
- Modify: `backend/app/modules/analytics/api.py`
- Modify: `backend/app/modules/export_center/api.py`
- Modify: `backend/app/api/v1/route_groups.py:148` (удалить дубль)
- Test: `tests/api/test_analytics_rbac.py`

**Справка:** RoleEnum-строки — `backend/app/models/tenant_billing.py:42-62+` (owner, admin, ot_pb_lead, ot_specialist, pb_engineer, ecologist, hr, lawyer, accountant, line_manager, worker, contractor_inspector, employee, client_admin, client_user, ot_head, …). ABAC-паттерн — `backend/app/api/routes/reports.py:31-41`. Прецеденты ролей: `_SUMMARY_ROLES` (`routes/dashboard.py:36`) = admin/owner/line_manager/hr/ot_pb_lead; `_OPS_DASHBOARD_ROLES` (`routes/operational_dashboard.py:19`) = +manager; `_REPORT_ROLES` (`routes/reports.py:31`) = +ot_specialist.

- [ ] **Step 1: Падающие тесты** `tests/api/test_analytics_rbac.py`:

```python
"""RBAC hardening: analytics + export_center routers; operational dedup pin."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory

ROUTE_GROUPS = (
    Path(__file__).resolve().parents[2] / "backend/app/api/v1/route_groups.py"
)


async def _tenant(sessionmaker, data_factory: TestDataFactory) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()


@pytest.mark.asyncio
async def test_analytics_read_rbac(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    await _tenant(sessionmaker, data_factory)
    worker = await make_auth_headers(RoleEnum.WORKER)
    for path in (
        "/api/v1/analytics/dashboard/executive",
        "/api/v1/analytics/dashboard/overdue",
        "/api/v1/analytics/trends/incidents",
    ):
        resp = await async_client.get(path, headers=worker)
        assert resp.status_code == status.HTTP_403_FORBIDDEN, path

    line_manager = await make_auth_headers(RoleEnum.LINE_MANAGER)
    ok = await async_client.get(
        "/api/v1/analytics/dashboard/overdue", headers=line_manager
    )
    assert ok.status_code == status.HTTP_200_OK
    hr = await make_auth_headers(RoleEnum.HR)
    ok2 = await async_client.get("/api/v1/analytics/trends/incidents", headers=hr)
    assert ok2.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_analytics_recompute_admin_only(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _tenant(sessionmaker, data_factory)
    line_manager = await make_auth_headers(RoleEnum.LINE_MANAGER)
    denied = await async_client.post("/api/v1/analytics/recompute", headers=line_manager)
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    admin = await make_auth_headers(RoleEnum.ADMIN)
    ok = await async_client.post("/api/v1/analytics/recompute", headers=admin)
    assert ok.status_code == status.HTTP_200_OK


@pytest.mark.asyncio
async def test_export_center_rbac(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _tenant(sessionmaker, data_factory)
    worker = await make_auth_headers(RoleEnum.WORKER)
    assert (
        await async_client.get("/api/v1/exports", headers=worker)
    ).status_code == status.HTTP_403_FORBIDDEN
    assert (
        await async_client.post(
            "/api/v1/exports",
            json={"export_type": "reports:test"},
            headers=worker,
        )
    ).status_code == status.HTTP_403_FORBIDDEN

    accountant = await make_auth_headers(RoleEnum.ACCOUNTANT)
    assert (
        await async_client.get("/api/v1/exports", headers=accountant)
    ).status_code == status.HTTP_200_OK

    admin = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/exports", json={"export_type": "reports:test"}, headers=admin
    )
    assert created.status_code == status.HTTP_201_CREATED


def test_operational_dashboard_registered_once() -> None:
    src = ROUTE_GROUPS.read_text(encoding="utf-8")
    assert src.count("(operational_dashboard.router") == 1
```

- [ ] **Step 2: Прогнать — FAIL** (403-ассерты падают: сейчас RBAC нет; дедуп-пин падает: 2 вхождения).

`& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_analytics_rbac.py -q`

- [ ] **Step 3: analytics/api.py — router-level guard + admin-guard на recompute.**

В начало файла (после существующих импортов) добавить:

```python
from app.core.security import abac
```

Перед `router = APIRouter(...)` добавить:

```python
def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


# Управленческие KPI: union прецедентов dashboard/operational/reports
# (_SUMMARY_ROLES + manager + ot_specialist). Worker/employee/client-роли не входят.
_ANALYTICS_READ_ROLES = [
    "admin",
    "owner",
    "hr",
    "ot_pb_lead",
    "line_manager",
    "ot_specialist",
    "manager",
]
_ANALYTICS_ADMIN_ROLES = ["admin", "owner"]

_ReadGuard = Depends(
    abac(_tenant_resource_id, required_roles=_ANALYTICS_READ_ROLES, action="read analytics")
)
_AdminGuard = Depends(
    abac(
        _tenant_resource_id,
        required_roles=_ANALYTICS_ADMIN_ROLES,
        action="recompute analytics",
    )
)
```

Заменить строку создания роутера на:

```python
router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[_ReadGuard])
```

(router-level guard покрывает ВСЕ роуты, включая будущий breakdown из Task 2). На `@router.post("/recompute")` добавить `dependencies=[_AdminGuard]`:

```python
@router.post("/recompute", dependencies=[_AdminGuard])
```

Сверь значения ролей со строками `RoleEnum` в `backend/app/models/tenant_billing.py` — если какой-то строки нет в enum (например "manager"), удали её из списка и отметь в отчёте (роль в ABAC сверяется со строкой роли пользователя; несуществующая строка безвредна, но чистота важнее).

- [ ] **Step 4: export_center/api.py — read/write-гейты.**

После существующих импортов добавить:

```python
from fastapi import Depends

from app.core.security import AccessContext, abac
```

(проверь фактические имеющиеся импорты — Depends уже импортирован; не дублируй). Перед `router = APIRouter(...)`:

```python
def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


# Read: все «офисные» роли (зеркало REPORTS_VIEW/DOCUMENT_EXPORT-матрицы фронта);
# исключены worker / employee / contractor_inspector.
_EXPORT_READ_ROLES = [
    "admin",
    "owner",
    "ot_pb_lead",
    "ot_head",
    "hr",
    "manager",
    "line_manager",
    "ot_specialist",
    "pb_engineer",
    "ecologist",
    "accountant",
    "lawyer",
    "client_admin",
    "client_user",
]
_EXPORT_WRITE_ROLES = [
    "admin",
    "owner",
    "ot_pb_lead",
    "ot_head",
    "ot_specialist",
    "pb_engineer",
    "ecologist",
    "accountant",
    "lawyer",
    "line_manager",
    "manager",
]

_ExportReadGuard = Depends(
    abac(_tenant_resource_id, required_roles=_EXPORT_READ_ROLES, action="read exports")
)
_ExportWriteGuard = Depends(
    abac(_tenant_resource_id, required_roles=_EXPORT_WRITE_ROLES, action="write exports")
)
```

Роутер: `router = APIRouter(prefix="/exports", tags=["exports"], dependencies=[_ExportReadGuard])` (read-гейт на всё). На write-роуты добавить `dependencies=[_ExportWriteGuard]`: `POST ""` (create_export), `POST "/schedules"`, `POST "/schedules/{schedule_id}/run-now"`, `POST "/kpis"`, `POST "/{job_id}/retry"`.

Сверь строки ролей с RoleEnum (как в Step 3); если в RoleEnum есть auditor-роль (например "auditor_ro") — добавь её в `_EXPORT_READ_ROLES`. ВАЖНО: read-роли обязаны включать роли поллинга со страницы конструктора отчётов (admin/owner/ot_specialist/line_manager — включены) и роли ExportsPage (REPORTS_VIEW-матрица — покрыта).

- [ ] **Step 5: route_groups.py — удалить строку 148** `(operational_dashboard.router, {"prefix": "", "tags": ["operational"]}),` (оставить регистрацию на строке ~151 без prefix). Никаких других правок.

- [ ] **Step 6: Прогнать** — `tests/api/test_analytics_rbac.py` → **5 passed**. Затем регресс существующих потребителей одним батчем: `tests/api/test_analytics_rbac.py tests/test_next62_analytics_search_export_center.py` (второй файл — существующие тесты analytics/export_center; если их auth-фикстуры дают роль вне новых списков — поправь ИХ на `RoleEnum.ADMIN`-заголовки, отметь в отчёте; если файла нет — найди regression-тесты по `grep -rl "analytics/dashboard" tests/` и прогони их).

- [ ] **Step 7: ruff + black на изменённые файлы. Commit** — `fix(p10-07): RBAC on analytics/export_center routers + dedupe operational_dashboard registration`

---

## Task 2: Breakdown-эндпоинт

**Files:**
- Create: `backend/app/modules/analytics/breakdown.py`
- Modify: `backend/app/modules/analytics/api.py` (один новый роут)
- Test: `tests/api/test_analytics_breakdown.py`

**Справка по FK (проверено):** `Incident.company_id`/`site_id` NOT NULL (`models/incidents.py:84-85`); `Prescription` — только `inspection_id` → join `Inspection` (`regulatory_inspection`: `company_id` NOT NULL, `site_id` nullable, `models/inspections.py:60-64,181`); `TrainingPlan.company_id` NOT NULL (`models/training.py:80`); `Risk.company_id` NOT NULL / `site_id` nullable (`models/risk.py:233-234`); `PPEIssue.person_id` → `Person.company_id` (`models/ppe.py:142`); подрядчики: `ContractorRegistry` (name, SoftDelete, `modules/contractors/models.py:27`) + `ContractorReadinessReadModel` (contractor_id, workers_blocked, missing_docs_count, missing_training_count, overdue_items_count, active_packages_count — `modules/projections/models.py:122`).

- [ ] **Step 1: Падающие тесты** `tests/api/test_analytics_breakdown.py`:

```python
"""Breakdown by company/site/contractor (P10-07 §24.2)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import (
    Company,
    Incident,
    IncidentStatus,
    RoleEnum,
    Site,
    TrainingPlan,
)
from app.models.risk import Risk
from tests.utils.factories import TestDataFactory

NOW = datetime.now(tz=timezone.utc)
BASE = "/api/v1/analytics/dashboard/breakdown"


async def _seed(sessionmaker, data_factory: TestDataFactory) -> dict[str, str]:
    from app.models.training import TrainingCourse

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        company = Company(tenant_id=tid, name="ООО Ромашка")
        session.add(company)
        await session.flush()
        s1 = Site(tenant_id=tid, company_id=company.id, name="Цех №1")
        s2 = Site(tenant_id=tid, company_id=company.id, name="Офис")
        session.add_all([s1, s2])
        await session.flush()
        session.add_all(
            [
                Incident(tenant_id=tid, company_id=company.id, site_id=s1.id,
                         title="Падение", occurred_at=NOW - timedelta(days=3)),
                Incident(tenant_id=tid, company_id=company.id, site_id=s1.id,
                         title="Порез", occurred_at=NOW - timedelta(days=40)),
                Incident(tenant_id=tid, company_id=company.id, site_id=s2.id,
                         title="Задымление", occurred_at=NOW - timedelta(days=1),
                         status=IncidentStatus.CLOSED),
                Risk(tenant_id=tid, company_id=company.id, site_id=s1.id,
                     hazard="Высота", probability=4, severity=4, level=16),
            ]
        )
        course = TrainingCourse(tenant_id=tid, title="ОТ-101")
        session.add(course)
        await session.flush()
        session.add(
            TrainingPlan(tenant_id=tid, company_id=company.id, course_id=course.id,
                         due_date=date.today() - timedelta(days=5))
        )
        await session.commit()
        return {"company_id": company.id, "s1": s1.id, "s2": s2.id}


@pytest.mark.asyncio
async def test_site_breakdown_counts_and_order(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory
):
    ids = await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=site", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["dimension"] == "site"
    assert body["total"] == 2
    first = body["items"][0]
    # Цех №1: 2 открытых инцидента + 1 high-риск → худший сверху
    assert first["id"] == ids["s1"]
    assert first["incidents_open"] == 2
    assert first["risks_high"] == 1
    assert first["total_issues"] == 3
    # Офис: закрытый инцидент не считается → нули, но строка присутствует
    second = body["items"][1]
    assert second["id"] == ids["s2"]
    assert second["incidents_open"] == 0
    assert second["total_issues"] == 0


@pytest.mark.asyncio
async def test_company_breakdown_includes_trainings(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    ids = await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=company", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    row = next(i for i in resp.json()["items"] if i["id"] == ids["company_id"])
    assert row["incidents_open"] == 2
    assert row["trainings_overdue"] == 1
    assert row["risks_high"] == 1


@pytest.mark.asyncio
async def test_date_window_narrows_incidents(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    ids = await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    date_from = (NOW - timedelta(days=7)).date().isoformat()
    resp = await async_client.get(
        f"{BASE}?dimension=site&date_from={date_from}", headers=headers
    )
    first = next(i for i in resp.json()["items"] if i["id"] == ids["s1"])
    assert first["incidents_open"] == 1  # 40-дневный инцидент отфильтрован


@pytest.mark.asyncio
async def test_contractor_breakdown_zero_row(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    from app.modules.contractors.models import ContractorRegistry

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            ContractorRegistry(tenant_id=str(tenant.id), name="СтройПодряд")
        )
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get(f"{BASE}?dimension=contractor", headers=headers)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["total"] == 1
    row = body["items"][0]
    assert row["name"] == "СтройПодряд"
    assert row["workers_blocked"] == 0 and row["total_issues"] == 0


@pytest.mark.asyncio
async def test_unknown_dimension_422_and_isolation(
    async_client, make_auth_headers, sessionmaker, data_factory
):
    await _seed(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    bad = await async_client.get(f"{BASE}?dimension=bogus", headers=headers)
    assert bad.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    # изоляция: метрики строго tenant-scoped — проверено WHERE в каждом запросе;
    # smoke: без dimension тоже 422 (обязательный параметр)
    missing = await async_client.get(BASE, headers=headers)
    assert missing.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
```

Примечание: если у `Site`/`Company` иные обязательные поля конструктора (посмотри модель в `backend/app/models/master_data.py`) или у `Incident.severity/investigation_stage` дефолты требуют явных значений — поправь СИД теста минимально. Если `Company`/`Site` имеют SoftDeleteMixin — ок (deleted_at default NULL).

- [ ] **Step 2: Прогнать — FAIL (404: роут не существует).**

- [ ] **Step 3: Реализация** `backend/app/modules/analytics/breakdown.py`:

```python
"""Breakdown управленческого дашборда: метрики в разрезе company/site/contractor.

Вычисляемый агрегат (P10-07 §24.2): на метрику — ОДИН SQL ``GROUP BY <dim_id>``
по живым таблицам, сшивка по id в Python, имена — из master-data. Не персистится,
ETag не нужен. Date-окно применяется ТОЛЬКО к incidents_open (occurred_at) —
overdue-метрики описывают состояние «на сегодня», окно к ним не применимо.
Contractor-разрез использует собственный набор метрик из
``ContractorReadinessReadModel`` (у пяти общих метрик нет FK на подрядчика).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master_data import Company, Person, Site
from app.models.models import (
    Incident,
    IncidentStatus,
    PPEIssue,
    PPEIssueStatus,
    Prescription,
    TrainingPlan,
)
from app.models.inspections import Inspection
from app.models.risk import Risk
from app.modules.contractors.models import ContractorRegistry
from app.modules.projections.models import ContractorReadinessReadModel

BREAKDOWN_DIMENSIONS = ("company", "site", "contractor")
BREAKDOWN_ROW_CAP = 200


async def _grouped_counts(session: AsyncSession, stmt) -> dict[str, int]:
    rows = (await session.execute(stmt)).all()
    return {str(key): int(value or 0) for key, value in rows if key is not None}


async def compute_breakdown(
    session: AsyncSession,
    tenant_id: str,
    dimension: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    if dimension == "contractor":
        return await _contractor_breakdown(session, tenant_id)

    today = date.today()
    if dimension == "company":
        dim_incidents = Incident.company_id
        dim_risks = Risk.company_id
        dim_prescriptions = Inspection.company_id
    else:  # site
        dim_incidents = Incident.site_id
        dim_risks = Risk.site_id
        dim_prescriptions = Inspection.site_id

    incidents_stmt = (
        select(dim_incidents, func.count())
        .where(
            Incident.tenant_id == tenant_id,
            Incident.deleted_at.is_(None),
            Incident.status.notin_([IncidentStatus.CLOSED, IncidentStatus.CANCELLED]),
        )
        .group_by(dim_incidents)
    )
    if date_from is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) >= date_from)
    if date_to is not None:
        incidents_stmt = incidents_stmt.where(func.date(Incident.occurred_at) <= date_to)

    risks_stmt = (
        select(dim_risks, func.count())
        .where(Risk.tenant_id == tenant_id, Risk.level >= 15)
        .group_by(dim_risks)
    )

    prescriptions_stmt = (
        select(dim_prescriptions, func.count())
        .select_from(Prescription)
        .join(Inspection, Inspection.id == Prescription.inspection_id)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.deleted_at.is_(None),
            Prescription.due_at.is_not(None),
            Prescription.due_at < today,
        )
        .group_by(dim_prescriptions)
    )

    incidents = await _grouped_counts(session, incidents_stmt)
    risks = await _grouped_counts(session, risks_stmt)
    prescriptions = await _grouped_counts(session, prescriptions_stmt)

    trainings: dict[str, int] = {}
    ppe: dict[str, int] = {}
    if dimension == "company":
        trainings = await _grouped_counts(
            session,
            select(TrainingPlan.company_id, func.count())
            .where(
                TrainingPlan.tenant_id == tenant_id,
                TrainingPlan.deleted_at.is_(None),
                TrainingPlan.due_date.is_not(None),
                TrainingPlan.due_date < today,
            )
            .group_by(TrainingPlan.company_id),
        )
        ppe = await _grouped_counts(
            session,
            select(Person.company_id, func.count())
            .select_from(PPEIssue)
            .join(Person, Person.id == PPEIssue.person_id)
            .where(
                PPEIssue.tenant_id == tenant_id,
                PPEIssue.deleted_at.is_(None),
                PPEIssue.status == PPEIssueStatus.ISSUED.value,
                PPEIssue.expires_at.is_not(None),
                func.date(PPEIssue.expires_at) < today,
            )
            .group_by(Person.company_id),
        )

    entity_model = Company if dimension == "company" else Site
    entity_stmt = select(entity_model.id, entity_model.name).where(
        entity_model.tenant_id == tenant_id
    )
    if hasattr(entity_model, "deleted_at"):
        entity_stmt = entity_stmt.where(entity_model.deleted_at.is_(None))
    entities = (await session.execute(entity_stmt)).all()

    items: list[dict[str, Any]] = []
    for entity_id, name in entities:
        eid = str(entity_id)
        row: dict[str, Any] = {
            "id": eid,
            "name": name,
            "incidents_open": incidents.get(eid, 0),
            "prescriptions_overdue": prescriptions.get(eid, 0),
            "risks_high": risks.get(eid, 0),
        }
        if dimension == "company":
            row["trainings_overdue"] = trainings.get(eid, 0)
            row["ppe_overdue"] = ppe.get(eid, 0)
        row["total_issues"] = sum(
            v for k, v in row.items() if k not in {"id", "name", "total_issues"}
        )
        items.append(row)

    items.sort(key=lambda r: (-r["total_issues"], r["name"]))
    return {"dimension": dimension, "items": items[:BREAKDOWN_ROW_CAP], "total": len(items)}


async def _contractor_breakdown(session: AsyncSession, tenant_id: str) -> dict[str, Any]:
    readiness_by_contractor = {
        row.contractor_id: row
        for row in (
            await session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == tenant_id
                )
            )
        ).scalars()
    }
    registry = (
        await session.execute(
            select(ContractorRegistry.id, ContractorRegistry.name).where(
                ContractorRegistry.tenant_id == tenant_id,
                ContractorRegistry.deleted_at.is_(None),
            )
        )
    ).all()

    items: list[dict[str, Any]] = []
    for contractor_id, name in registry:
        r = readiness_by_contractor.get(contractor_id)
        row = {
            "id": str(contractor_id),
            "name": name,
            "workers_blocked": int(r.workers_blocked) if r else 0,
            "missing_docs": int(r.missing_docs_count) if r else 0,
            "missing_training": int(r.missing_training_count) if r else 0,
            "overdue_items": int(r.overdue_items_count) if r else 0,
            "active_packages": int(r.active_packages_count) if r else 0,
        }
        row["total_issues"] = (
            row["workers_blocked"]
            + row["missing_docs"]
            + row["missing_training"]
            + row["overdue_items"]
        )
        items.append(row)

    items.sort(key=lambda r: (-r["total_issues"], r["name"]))
    return {
        "dimension": "contractor",
        "items": items[:BREAKDOWN_ROW_CAP],
        "total": len(items),
    }
```

Проверь фактические имена/пути импортов (`Person`/`Company`/`Site` из `app.models.master_data`; `Inspection` из `app.models.inspections` — в models.py может быть ре-экспортирован конфликтно с checks.Inspection: analytics/services.py:13 импортирует `Inspection` из `app.models.models` и это **checks.Inspection**! Для предписаний нужен `app.models.inspections.Inspection` (regulatory) — импортируй его ЯВНО из модуля, не из models.py, и проверь `PPEIssue.status` — VARCHAR со строковыми значениями (`PPEIssueStatus.ISSUED.value`), см. `models/ppe.py:157`).

- [ ] **Step 4: Роут** в `backend/app/modules/analytics/api.py` (перед `@router.post("/recompute")`):

```python
from fastapi import HTTPException, status as http_status

from app.core.errors import api_problem_detail
from app.modules.analytics.breakdown import BREAKDOWN_DIMENSIONS, compute_breakdown
```

(импорты — в общий блок сверху) и роут:

```python
@router.get("/dashboard/breakdown")
async def dashboard_breakdown(
    dimension: str = Query(...),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    if dimension not in BREAKDOWN_DIMENSIONS:
        raise HTTPException(
            http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="breakdown_dimension_unknown",
                message=f"Unknown dimension: {dimension}",
                error_type="analytics",
            ),
        )
    return await compute_breakdown(
        session, str(tenant.id), dimension, date_from=date_from, date_to=date_to
    )
```

- [ ] **Step 5: Прогнать** оба файла батчем: `tests/api/test_analytics_breakdown.py tests/api/test_analytics_rbac.py` → 10 passed.
- [ ] **Step 6: ruff + black. Commit** — `feat(p10-07): analytics breakdown endpoint (company/site/contractor)`

---

## Task 3: recharts + TrendLineChart + ResizeObserver-полифилл

**Files:**
- Modify: `frontend/package.json` + `frontend/package-lock.json` (npm install)
- Modify: `frontend/vitest.setup.ts`
- Create: `frontend/src/components/analytics/TrendLineChart.tsx`
- Test: `frontend/src/components/analytics/TrendLineChart.test.tsx`

- [ ] **Step 1:** `cd "<worktree>/frontend" && npm install recharts` (Bash, абсолютный cwd; коммитить package.json + package-lock.json вместе).

- [ ] **Step 2: Полифилл** — в конец `frontend/vitest.setup.ts`:

```typescript
if (!window.ResizeObserver) {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}
```

- [ ] **Step 3: Падающий тест** `frontend/src/components/analytics/TrendLineChart.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { TrendLineChart } from "@/components/analytics/TrendLineChart";

describe("TrendLineChart", () => {
  it("renders the title and an empty hint when there is no data", () => {
    render(<TrendLineChart title="Инциденты" series={[]} />);
    expect(screen.getByText("Инциденты")).toBeInTheDocument();
    expect(screen.getByText("Нет данных за период")).toBeInTheDocument();
  });

  it("renders a chart container when data is present", () => {
    render(
      <TrendLineChart
        title="Инциденты"
        series={[
          { date: "2026-07-01", value: 2 },
          { date: "2026-07-02", value: 5 }
        ]}
      />
    );
    expect(screen.getByText("Инциденты")).toBeInTheDocument();
    expect(screen.getByTestId("trend-chart-Инциденты")).toBeInTheDocument();
    expect(screen.queryByText("Нет данных за период")).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 4: Реализация** `frontend/src/components/analytics/TrendLineChart.tsx`:

```tsx
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";

export interface TrendPoint {
  date: string; // ISO
  value: number;
}

interface TrendLineChartProps {
  title: string;
  series: TrendPoint[];
  height?: number;
}

const shortDate = (iso: string): string => {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
};

/** Линейный график одного тренда (12 точек /analytics/trends/*). jsdom не даёт
 * размеров контейнеру — тесты проверяют заголовок/наличие контейнера, не SVG. */
export function TrendLineChart({ title, series, height = 220 }: TrendLineChartProps) {
  return (
    <div className="rounded-lg border bg-card p-4">
      <p className="mb-2 text-sm font-medium">{title}</p>
      {series.length === 0 ? (
        <p className="text-sm text-muted-foreground">Нет данных за период</p>
      ) : (
        <div data-testid={`trend-chart-${title}`} style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={series} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" tickFormatter={shortDate} fontSize={11} />
              <YAxis allowDecimals={false} fontSize={11} />
              <Tooltip
                labelFormatter={(label) => shortDate(String(label))}
                formatter={(value) => [String(value), "Значение"]}
              />
              <Line
                type="monotone"
                dataKey="value"
                stroke="currentColor"
                className="text-primary"
                strokeWidth={2}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
```

(если `stroke="currentColor"` + className на Line не красит линию — допустимо заменить на фиксированный `stroke="#2563eb"`; сверь, как проект задаёт primary-цвет.)

- [ ] **Step 5: Прогнать** — `npx vitest run src/components/analytics/TrendLineChart.test.tsx` → 2 passed. Затем `npx tsc --noEmit` → 0.
- [ ] **Step 6: Commit** — `feat(p10-07): add recharts + TrendLineChart wrapper + ResizeObserver test polyfill`

---

## Task 4: analyticsApi + DTO

**Files:**
- Create: `frontend/src/types/dto/analytics.ts`
- Create: `frontend/src/api/analyticsApi.ts`
- Test: `frontend/src/__tests__/analyticsApi.test.ts`

- [ ] **Step 1: Падающий тест** `frontend/src/__tests__/analyticsApi.test.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from "vitest";

const getMock = vi.fn();

vi.mock("@/api/client", () => ({
  apiClient: { get: (...args: unknown[]) => getMock(...args) }
}));

import { analyticsApi } from "@/api/analyticsApi";

describe("analyticsApi", () => {
  beforeEach(() => {
    getMock.mockReset().mockResolvedValue({ data: {} });
  });

  it("fetches dashboards with filters as params (undefined omitted)", async () => {
    await analyticsApi.getDashboard("overdue", { company_id: "c1", date_from: "2026-07-01" });
    expect(getMock).toHaveBeenCalledWith("/analytics/dashboard/overdue", {
      params: { company_id: "c1", date_from: "2026-07-01" }
    });
    await analyticsApi.getDashboard("executive", {});
    expect(getMock).toHaveBeenLastCalledWith("/analytics/dashboard/executive", { params: {} });
  });

  it("fetches trends with period (no filters — endpoint is tenant-wide)", async () => {
    await analyticsApi.getTrend("incidents", "weekly");
    expect(getMock).toHaveBeenCalledWith("/analytics/trends/incidents", {
      params: { period: "weekly" }
    });
  });

  it("fetches breakdown with dimension and window", async () => {
    await analyticsApi.getBreakdown("site", { date_from: "2026-07-01" });
    expect(getMock).toHaveBeenCalledWith("/analytics/dashboard/breakdown", {
      params: { dimension: "site", date_from: "2026-07-01" }
    });
  });

  it("fetches filter directories", async () => {
    await analyticsApi.getCompanies();
    expect(getMock).toHaveBeenCalledWith("/companies", { params: { limit: 200 } });
    await analyticsApi.getSites();
    expect(getMock).toHaveBeenCalledWith("/sites", { params: { limit: 200 } });
    await analyticsApi.getContractors();
    expect(getMock).toHaveBeenCalledWith("/contractors/registry", { params: { limit: 200 } });
  });
});
```

- [ ] **Step 2: Прогнать — FAIL.**

- [ ] **Step 3: DTO** `frontend/src/types/dto/analytics.ts`:

```typescript
export interface AnalyticsFiltersDto {
  company_id?: string;
  site_id?: string;
  contractor_id?: string;
  date_from?: string;
  date_to?: string;
}

export interface DashboardWidgetsDto {
  name?: string;
  widgets: Record<string, number>;
}

export interface ExecutiveDashboardDto {
  snapshot_date: string;
  widgets: Record<string, unknown>;
  dashboard: DashboardWidgetsDto;
}

export interface TrendPointDto {
  date: string;
  value: number;
}

export interface TrendSeriesDto {
  metric: string;
  period: "daily" | "weekly" | "monthly";
  series: TrendPointDto[];
}

export interface BreakdownRowDto {
  id: string;
  name: string;
  total_issues: number;
  [metric: string]: string | number;
}

export interface BreakdownDto {
  dimension: "company" | "site" | "contractor";
  items: BreakdownRowDto[];
  total: number;
}

export interface DirectoryItemDto {
  id: string;
  name: string;
}
```

- [ ] **Step 4: Клиент** `frontend/src/api/analyticsApi.ts`:

```typescript
import { apiClient } from "@/api/client";
import type {
  AnalyticsFiltersDto,
  BreakdownDto,
  DashboardWidgetsDto,
  DirectoryItemDto,
  ExecutiveDashboardDto,
  TrendSeriesDto
} from "@/types/dto/analytics";

const clean = (filters: AnalyticsFiltersDto): Record<string, string> => {
  const params: Record<string, string> = {};
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== null && value !== "") params[key] = value;
  }
  return params;
};

type DirectoryPage = { items?: DirectoryItemDto[]; total?: number };

export const analyticsApi = {
  getDashboard: async <T = DashboardWidgetsDto>(
    name: "executive" | "overdue" | "sla-load",
    filters: AnalyticsFiltersDto
  ): Promise<T> => {
    const { data } = await apiClient.get<T>(`/analytics/dashboard/${name}`, {
      params: clean(filters)
    });
    return data;
  },
  getExecutive: async (filters: AnalyticsFiltersDto): Promise<ExecutiveDashboardDto> => {
    const { data } = await apiClient.get<ExecutiveDashboardDto>(
      "/analytics/dashboard/executive",
      { params: clean(filters) }
    );
    return data;
  },
  getTrend: async (
    metric: "incidents" | "compliance" | "packages" | "trainings" | "inspections" | "ppe",
    period: "daily" | "weekly" | "monthly"
  ): Promise<TrendSeriesDto> => {
    const { data } = await apiClient.get<TrendSeriesDto>(`/analytics/trends/${metric}`, {
      params: { period }
    });
    return data;
  },
  getBreakdown: async (
    dimension: "company" | "site" | "contractor",
    window: Pick<AnalyticsFiltersDto, "date_from" | "date_to">
  ): Promise<BreakdownDto> => {
    const { data } = await apiClient.get<BreakdownDto>("/analytics/dashboard/breakdown", {
      params: { dimension, ...clean(window) }
    });
    return data;
  },
  getCompanies: async (): Promise<DirectoryPage> => {
    const { data } = await apiClient.get<DirectoryPage>("/companies", {
      params: { limit: 200 }
    });
    return data;
  },
  getSites: async (): Promise<DirectoryPage> => {
    const { data } = await apiClient.get<DirectoryPage>("/sites", {
      params: { limit: 200 }
    });
    return data;
  },
  getContractors: async (): Promise<DirectoryPage> => {
    const { data } = await apiClient.get<DirectoryPage>("/contractors/registry", {
      params: { limit: 200 }
    });
    return data;
  }
};
```

Примечание: в тесте `getDashboard("executive", {})` возвращает generic-структуру — фактически хаб зовёт `getExecutive`. Проверь фактические path/shape `/sites`-списка (grep `prefix="/sites"` или `path="/sites"` в `backend/app/api/routes/`) и форму ответа `/contractors/registry` (items/total?) — при расхождении поправь клиент И тест синхронно, отметь в отчёте.

- [ ] **Step 5: Прогнать** — 4 passed. `npx tsc --noEmit` → 0.
- [ ] **Step 6: Commit** — `feat(p10-07): typed analyticsApi client + DTOs`

---

## Task 5: ManagementDashboardPage + ANALYTICS_VIEW + wiring

**Files:**
- Modify: `frontend/src/permissions/permissions.ts`
- Create: `frontend/src/pages/analytics/ManagementDashboardPage.tsx`
- Modify: `frontend/src/router/pageRegistry.tsx`
- Modify: `frontend/src/router/routeGroups.tsx`
- Modify: `frontend/src/router/navigationConfig.ts`
- Test: `frontend/src/__tests__/ManagementDashboardPage.test.tsx`

- [ ] **Step 1: Право.** В `permissions.ts`: в объект PERMISSIONS добавить `ANALYTICS_VIEW: "analytics.view",` (рядом с DASHBOARD_VIEW, строка ~2). В ROLE_PERMISSIONS добавить `PERMISSIONS.ANALYTICS_VIEW` в списки ролей `ot_specialist`, `line_manager`, `hr` (owner/admin/ot_pb_head получают через ALL_PERMISSIONS автоматически). Другие роли НЕ трогать.

- [ ] **Step 2: Падающие тесты** `frontend/src/__tests__/ManagementDashboardPage.test.tsx`:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

const api = {
  getExecutive: vi.fn(),
  getDashboard: vi.fn(),
  getTrend: vi.fn(),
  getBreakdown: vi.fn(),
  getCompanies: vi.fn(),
  getSites: vi.fn(),
  getContractors: vi.fn()
};

vi.mock("@/api/analyticsApi", () => ({ analyticsApi: api }));

import ManagementDashboardPage from "@/pages/analytics/ManagementDashboardPage";

const TREND = (metric: string) => ({
  metric,
  period: "daily" as const,
  series: [
    { date: "2026-07-01", value: 1 },
    { date: "2026-07-02", value: 3 }
  ]
});

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.getExecutive.mockResolvedValue({
    snapshot_date: "2026-07-11",
    widgets: {},
    dashboard: {
      name: "executive",
      widgets: {
        packages_total: 12,
        overdue_compliance_items: 3,
        open_incidents: 2,
        open_inspections: 1
      }
    }
  });
  api.getDashboard.mockImplementation(async (name: string) =>
    name === "overdue"
      ? {
          name,
          widgets: {
            trainings_overdue: 4,
            ppe_overdue: 2,
            prescriptions_overdue: 1,
            plan_tasks_overdue: 0,
            overdue_compliance_items: 3
          }
        }
      : {
          name,
          widgets: { workflow_open: 5, workflow_sla_breached: 1, plan_tasks_overdue: 0 }
        }
  );
  api.getTrend.mockImplementation(async (metric: string) => TREND(metric));
  api.getBreakdown.mockResolvedValue({
    dimension: "site",
    items: [
      { id: "s1", name: "Цех №1", incidents_open: 2, risks_high: 1, prescriptions_overdue: 0, total_issues: 3 },
      { id: "s2", name: "Офис", incidents_open: 0, risks_high: 0, prescriptions_overdue: 0, total_issues: 0 }
    ],
    total: 2
  });
  api.getCompanies.mockResolvedValue({ items: [{ id: "c1", name: "ООО Ромашка" }], total: 1 });
  api.getSites.mockResolvedValue({ items: [{ id: "s1", name: "Цех №1" }], total: 1 });
  api.getContractors.mockResolvedValue({ items: [{ id: "k1", name: "СтройПодряд" }], total: 1 });
});

function renderPage() {
  return render(
    <MemoryRouter>
      <ManagementDashboardPage />
    </MemoryRouter>
  );
}

describe("ManagementDashboardPage", () => {
  it("renders KPI cards from executive/overdue/sla-load", async () => {
    renderPage();
    expect(await screen.findByText("Открытые инциденты")).toBeInTheDocument();
    expect(screen.getByText("Просроченное обучение")).toBeInTheDocument();
    expect(screen.getByText("Нарушен SLA")).toBeInTheDocument();
  });

  it("renders six trend charts and switches period", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    expect(api.getTrend).toHaveBeenCalledTimes(6);
    await user.click(screen.getByRole("button", { name: "Неделя" }));
    await waitFor(() => expect(api.getTrend).toHaveBeenCalledWith("incidents", "weekly"));
  });

  it("passes filters to dashboard requests", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Открытые инциденты");
    await user.selectOptions(screen.getByLabelText("Компания"), "c1");
    await waitFor(() =>
      expect(api.getExecutive).toHaveBeenLastCalledWith(
        expect.objectContaining({ company_id: "c1" })
      )
    );
  });

  it("renders breakdown table and switches dimension", async () => {
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText("Цех №1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "По подрядчикам" }));
    await waitFor(() =>
      expect(api.getBreakdown).toHaveBeenLastCalledWith("contractor", expect.anything())
    );
  });

  it("applies row click as a page filter (site drill-down)", async () => {
    const user = userEvent.setup();
    renderPage();
    const row = await screen.findByText("Цех №1");
    await user.click(row);
    await waitFor(() =>
      expect(api.getExecutive).toHaveBeenLastCalledWith(
        expect.objectContaining({ site_id: "s1" })
      )
    );
  });

  it("links to the profile sub-dashboards", async () => {
    renderPage();
    await screen.findByText("Открытые инциденты");
    const link = screen.getByRole("link", { name: /Executive/i });
    expect(link).toHaveAttribute("href", "/dashboard/executive");
  });
});
```

- [ ] **Step 3: Прогнать — FAIL.**

- [ ] **Step 4: Страница** `frontend/src/pages/analytics/ManagementDashboardPage.tsx` (house-style single-file; сверь импорты общих компонентов по `frontend/src/pages/medical/MedicalPage.tsx` — named vs default; Breadcrumb из `@/components/ui/breadcrumb` как в ReportsPage):

```tsx
import { useCallback, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { analyticsApi } from "@/api/analyticsApi";
import { TrendLineChart } from "@/components/analytics/TrendLineChart";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAsyncResource } from "@/hooks/useAsyncResource";
import type {
  AnalyticsFiltersDto,
  BreakdownDto,
  DashboardWidgetsDto,
  DirectoryItemDto,
  ExecutiveDashboardDto,
  TrendSeriesDto
} from "@/types/dto/analytics";

const TREND_METRICS = [
  { key: "incidents", title: "Инциденты" },
  { key: "compliance", title: "Просрочки соответствия" },
  { key: "packages", title: "Пакеты документов" },
  { key: "trainings", title: "Просроченное обучение" },
  { key: "inspections", title: "Проверки" },
  { key: "ppe", title: "СИЗ" }
] as const;

const KPI_LABELS: Record<string, string> = {
  packages_total: "Пакеты документов",
  overdue_compliance_items: "Блокирующие несоответствия",
  open_incidents: "Открытые инциденты",
  open_inspections: "Открытые проверки",
  trainings_overdue: "Просроченное обучение",
  ppe_overdue: "Просроченные СИЗ",
  prescriptions_overdue: "Просроченные предписания",
  plan_tasks_overdue: "Просроченные задачи планов",
  workflow_open: "Открытые workflow-задачи",
  workflow_sla_breached: "Нарушен SLA"
};

const BREAKDOWN_METRIC_LABELS: Record<string, string> = {
  incidents_open: "Инциденты",
  prescriptions_overdue: "Предписания",
  trainings_overdue: "Обучение",
  ppe_overdue: "СИЗ",
  risks_high: "Высокие риски",
  workers_blocked: "Блокированные работники",
  missing_docs: "Нет документов",
  missing_training: "Нет обучения",
  overdue_items: "Просрочки",
  active_packages: "Активные пакеты"
};

const DIMENSIONS = [
  { key: "company", label: "По компаниям" },
  { key: "site", label: "По объектам" },
  { key: "contractor", label: "По подрядчикам" }
] as const;

const PERIODS = [
  { key: "daily", label: "День" },
  { key: "weekly", label: "Неделя" },
  { key: "monthly", label: "Месяц" }
] as const;

const SUB_DASHBOARDS = [
  { to: "/dashboard/executive", label: "Executive" },
  { to: "/dashboard/safety", label: "Безопасность" },
  { to: "/dashboard/training", label: "Обучение" },
  { to: "/dashboard/ppe", label: "СИЗ" },
  { to: "/dashboard/client-delivery", label: "Клиентская доставка" }
] as const;

type Period = (typeof PERIODS)[number]["key"];
type Dimension = (typeof DIMENSIONS)[number]["key"];

export default function ManagementDashboardPage() {
  const [filters, setFilters] = useState<AnalyticsFiltersDto>({});
  const [period, setPeriod] = useState<Period>("daily");
  const [dimension, setDimension] = useState<Dimension>("site");

  const companiesRes = useAsyncResource<{ items?: DirectoryItemDto[] }>({
    loader: useCallback(() => analyticsApi.getCompanies(), []),
    initialData: { items: [] },
    errorMessage: "Не удалось загрузить компании"
  });
  const sitesRes = useAsyncResource<{ items?: DirectoryItemDto[] }>({
    loader: useCallback(() => analyticsApi.getSites(), []),
    initialData: { items: [] },
    errorMessage: "Не удалось загрузить объекты"
  });
  const contractorsRes = useAsyncResource<{ items?: DirectoryItemDto[] }>({
    loader: useCallback(() => analyticsApi.getContractors(), []),
    initialData: { items: [] },
    errorMessage: "Не удалось загрузить подрядчиков"
  });

  const executiveRes = useAsyncResource<ExecutiveDashboardDto | null>({
    loader: useCallback(() => analyticsApi.getExecutive(filters), [filters]),
    initialData: null,
    errorMessage: "Не удалось загрузить сводные показатели"
  });
  const overdueRes = useAsyncResource<DashboardWidgetsDto | null>({
    loader: useCallback(() => analyticsApi.getDashboard("overdue", filters), [filters]),
    initialData: null,
    errorMessage: "Не удалось загрузить просрочки"
  });
  const slaRes = useAsyncResource<DashboardWidgetsDto | null>({
    loader: useCallback(() => analyticsApi.getDashboard("sla-load", filters), [filters]),
    initialData: null,
    errorMessage: "Не удалось загрузить SLA-нагрузку"
  });
  const trendsRes = useAsyncResource<TrendSeriesDto[]>({
    loader: useCallback(
      () => Promise.all(TREND_METRICS.map((m) => analyticsApi.getTrend(m.key, period))),
      [period]
    ),
    initialData: [],
    errorMessage: "Не удалось загрузить тренды"
  });
  const breakdownRes = useAsyncResource<BreakdownDto | null>({
    loader: useCallback(
      () =>
        analyticsApi.getBreakdown(dimension, {
          date_from: filters.date_from,
          date_to: filters.date_to
        }),
      [dimension, filters.date_from, filters.date_to]
    ),
    initialData: null,
    errorMessage: "Не удалось загрузить разрез"
  });

  const kpiCards = useMemo(() => {
    const widgets: Record<string, number> = {
      ...(executiveRes.data?.dashboard?.widgets ?? {}),
      ...(overdueRes.data?.widgets ?? {}),
      ...(slaRes.data?.widgets ?? {})
    };
    return Object.entries(KPI_LABELS)
      .filter(([key]) => key in widgets)
      .map(([key, label]) => ({ key, label, value: widgets[key] }));
  }, [executiveRes.data, overdueRes.data, slaRes.data]);

  const breakdown = breakdownRes.data;
  const metricKeys = useMemo(() => {
    if (!breakdown || breakdown.items.length === 0) return [];
    return Object.keys(breakdown.items[0]).filter(
      (k) => !["id", "name", "total_issues"].includes(k)
    );
  }, [breakdown]);
  const maxIssues = useMemo(
    () => Math.max(1, ...(breakdown?.items.map((i) => i.total_issues) ?? [1])),
    [breakdown]
  );

  const setFilter = useCallback((key: keyof AnalyticsFiltersDto, value: string) => {
    setFilters((prev) => {
      const next = { ...prev };
      if (value) next[key] = value;
      else delete next[key];
      return next;
    });
  }, []);

  const applyRowFilter = useCallback(
    (rowId: string) => {
      if (dimension === "company") setFilter("company_id", rowId);
      else if (dimension === "site") setFilter("site_id", rowId);
      else setFilter("contractor_id", rowId);
    },
    [dimension, setFilter]
  );

  if (companiesRes.loading || executiveRes.loading) return <LoadingScreen />;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Управленческая аналитика</CardTitle>
          <CardDescription>
            KPI, тренды и разрез по компаниям / объектам / подрядчикам (vNext §24.2).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label htmlFor="ma-company">Компания</Label>
              <select
                id="ma-company"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={filters.company_id ?? ""}
                onChange={(e) => setFilter("company_id", e.target.value)}
              >
                <option value="">— все —</option>
                {(companiesRes.data?.items ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="ma-site">Объект</Label>
              <select
                id="ma-site"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={filters.site_id ?? ""}
                onChange={(e) => setFilter("site_id", e.target.value)}
              >
                <option value="">— все —</option>
                {(sitesRes.data?.items ?? []).map((s) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="ma-contractor">Подрядчик</Label>
              <select
                id="ma-contractor"
                className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                value={filters.contractor_id ?? ""}
                onChange={(e) => setFilter("contractor_id", e.target.value)}
              >
                <option value="">— все —</option>
                {(contractorsRes.data?.items ?? []).map((k) => (
                  <option key={k.id} value={k.id}>{k.name}</option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="ma-from">С</Label>
              <Input
                id="ma-from"
                type="date"
                value={filters.date_from ?? ""}
                onChange={(e) => setFilter("date_from", e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="ma-to">По</Label>
              <Input
                id="ma-to"
                type="date"
                value={filters.date_to ?? ""}
                onChange={(e) => setFilter("date_to", e.target.value)}
              />
            </div>
            <Button variant="outline" onClick={() => setFilters({})}>Сбросить</Button>
          </div>
        </CardContent>
      </Card>

      {executiveRes.error ? (
        <ErrorState error={executiveRes.error} onRetry={executiveRes.reload} />
      ) : (
        <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
          {kpiCards.map((card) => (
            <Card key={card.key}>
              <CardHeader className="pb-2">
                <CardDescription>{card.label}</CardDescription>
                <CardTitle className="text-2xl">{card.value}</CardTitle>
              </CardHeader>
            </Card>
          ))}
        </div>
      )}

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Тренды</CardTitle>
            <div className="flex gap-1">
              {PERIODS.map((p) => (
                <Button
                  key={p.key}
                  size="sm"
                  variant={period === p.key ? "default" : "outline"}
                  aria-pressed={period === p.key}
                  onClick={() => setPeriod(p.key)}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {trendsRes.error ? (
            <ErrorState error={trendsRes.error} onRetry={trendsRes.reload} />
          ) : (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {TREND_METRICS.map((m, idx) => (
                <TrendLineChart
                  key={m.key}
                  title={m.title}
                  series={trendsRes.data?.[idx]?.series ?? []}
                />
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle>Разрез</CardTitle>
            <div className="flex gap-1">
              {DIMENSIONS.map((d) => (
                <Button
                  key={d.key}
                  size="sm"
                  variant={dimension === d.key ? "default" : "outline"}
                  aria-pressed={dimension === d.key}
                  onClick={() => setDimension(d.key)}
                >
                  {d.label}
                </Button>
              ))}
            </div>
          </div>
          <CardDescription>Клик по строке применяет её как фильтр страницы.</CardDescription>
        </CardHeader>
        <CardContent>
          {breakdownRes.error ? (
            <ErrorState error={breakdownRes.error} onRetry={breakdownRes.reload} />
          ) : !breakdown || breakdown.items.length === 0 ? (
            <EmptyState title="Нет данных" description="В этом разрезе пока пусто." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-muted-foreground">
                    <th className="py-2 pr-4">Название</th>
                    {metricKeys.map((k) => (
                      <th key={k} className="py-2 pr-4">
                        {BREAKDOWN_METRIC_LABELS[k] ?? k}
                      </th>
                    ))}
                    <th className="py-2">Всего проблем</th>
                  </tr>
                </thead>
                <tbody>
                  {breakdown.items.map((row) => (
                    <tr
                      key={row.id}
                      className="cursor-pointer border-b last:border-0 hover:bg-muted/50"
                      onClick={() => applyRowFilter(row.id)}
                    >
                      <td className="py-2 pr-4">{row.name}</td>
                      {metricKeys.map((k) => (
                        <td key={k} className="py-2 pr-4">{row[k]}</td>
                      ))}
                      <td className="py-2">
                        <div className="flex items-center gap-2">
                          <span className="w-8 text-right">{row.total_issues}</span>
                          <div className="h-2 flex-1 rounded bg-muted">
                            <div
                              className="h-2 rounded bg-primary"
                              style={{ width: `${(row.total_issues / maxIssues) * 100}%` }}
                            />
                          </div>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Профильные дашборды</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex flex-wrap gap-2">
            {SUB_DASHBOARDS.map((d) => (
              <Button key={d.to} asChild variant="outline">
                <Link to={d.to}>{d.label}</Link>
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 5: Wiring.**
- `pageRegistry.tsx`: `export const ManagementDashboardPage = lazy(() => import("@/pages/analytics/ManagementDashboardPage"));`
- `routeGroups.tsx`: новая группа `{ permission: PERMISSIONS.ANALYTICS_VIEW, routes: [<Route key="/analytics" path="/analytics" element={<ManagementDashboardPage />} />] }` (+ импорт из pageRegistry). Проверь: существующий `/analytics/trends` (группа REPORTS_VIEW) остаётся доступным — react-router v6 матчит точные пути; добавь smoke-проверку в существующий router-тест только если он есть (`AppRouterSmoke.test.tsx` — посмотри его паттерн; если добавление тривиально — добавь маршрут в его список).
- `navigationConfig.ts`: в «Бизнес и аналитика» после «Тренды»: `{ label: "Управленческая аналитика", to: "/analytics", icon: Activity, permission: PERMISSIONS.ANALYTICS_VIEW },` (Activity уже импортирован — проверь; иначе возьми импортированный подходящий).

- [ ] **Step 6: Прогнать** — `npx vitest run src/__tests__/ManagementDashboardPage.test.tsx src/__tests__/analyticsApi.test.ts src/components/analytics/TrendLineChart.test.tsx` → 12 passed. `npx tsc --noEmit` → 0.
- [ ] **Step 7: Commit** — `feat(p10-07): ManagementDashboardPage (/analytics) + ANALYTICS_VIEW permission + nav`

---

## Task 6 (контроллер): гейты + docs

- [ ] Backend-регресс батчами ≤5 (PowerShell): Б1 `tests/api/test_analytics_rbac.py tests/api/test_analytics_breakdown.py` + существующие analytics/export-тесты (`grep -rl "analytics/dashboard\|/exports" tests/ | head`); Б2 смежные (`tests/test_next62_analytics_search_export_center.py` если существует).
- [ ] ruff + black.
- [ ] OpenAPI baseline re-snap + compare: ожидание — +1 роут (breakdown), МИНУС дубль operational_dashboard operationId (диф не чисто аддитивный — ожидаемо, зафиксировать в handoff; warning «Duplicate Operation ID get_operational_dashboard» должен исчезнуть).
- [ ] PG16-гейт НЕ гонять (миграций нет).
- [ ] Frontend: полный vitest (НЕ параллельно с pytest) → tsc → build (зафиксировать дельту бандла от recharts).
- [ ] Docs: roadmap P10-07 строка (управленческие дашборды shipped; «Остаётся» сужается), CHANGELOG (2026-07-11), handoff-блок AI_IMPLEMENTATION_REPORT.md.
- [ ] Финальное whole-slice ревью; после мержа — dismiss чипа task_5f3fcf25 (superseded Task 1).

---

## Проверка соответствия спеке (self-check)

- §4 RBAC → Task 1. §5 breakdown → Task 2. §6 chart-слой → Task 3. §7 хаб/право/wiring → Task 5 (+Task 4 клиент). §8 тест-план → тесты задач. §9 гейты → Task 6. Отложенное (§3) не реализовывать.
