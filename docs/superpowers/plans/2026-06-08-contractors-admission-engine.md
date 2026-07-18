# Подрядчики Срез-1 — движок допуска: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Заменить заглушку готовности подрядчиков настоящим движком допуска (вердикт ALLOWED/WARNING/BLOCKED с перекрёстной сверкой статус-флага и дедлайна), добавить жёсткий гейт допуска, наполнить read-модель и добавить ежедневный beat.

**Architecture:** Новый домен `domains/contractors/` (чистый `lifecycle.py`) + сервис `services/contractor_admission.py` (зеркало `services/person_admission.py`). Общий `domains/shared.py` (лифт `classify`/`ContingentItemStatus` из medical). Аддитивно поверх существующих моделей/CRUD; миграция БД не требуется.

**Tech Stack:** Python 3.12 (CI; локально 3.13.7/.venv), FastAPI, SQLAlchemy async, Celery, pytest. Запуск тестов локально: PowerShell→файл, `-p no:xdist --timeout`.

---

## Контекст для реализатора (прочесть перед началом)

Источники истины в коде:
- Модели подрядчиков: `backend/app/modules/contractors/models.py:12-91`. `ComplianceStatus = valid/pending/expired/blocked`. `ContractorEmployee`: `access_status`, `training_status`, `medical_status`, `last_training_at`, `next_medical_at`. (У `position` нет id — только строка; СОУТ-нормы в Срезе-1 не используем.)
- Шаблон чистого FSM: `backend/app/domains/medical/lifecycle.py:103-122` (`ContingentItemStatus`, `classify`).
- Шаблон сервиса-гейта: `backend/app/services/person_admission.py:36-244` (raise `ValueError({"code":"requirements_not_met","details":[...]})`).
- Перевод гейта в HTTP: `backend/app/api/routes/packs.py:306-325` — ловит `ValueError`, поднимает **HTTP 409 CONFLICT** с detail-словарём `{code, error_code, message, type, details}`. **Используем 409, как в packs (а не 422)** — это конвенция репозитория.
- Роуты подрядчиков: `backend/app/api/routes/contractors.py:1-329` (деп `SessionDep`/`TenantDep`, `ReaderAccess`/`WriterAccess`, fetch сотрудника `:239-257`).
- Feature-flag-гейт: `backend/app/api/routes/medical.py:68-70` (`require_medical_feature` + `is_feature_enabled`).
- Read-модель: `backend/app/modules/projections/models.py:104-119`. Колонки для наполнения: `workers_total`, `workers_ready`, `workers_blocked`, `missing_training_count`, `overdue_items_count`. `missing_docs_count` оставить 0 (документы — Срез-2). `active_packages_count` сохранить.
- Заглушка проекции: `backend/app/modules/projections/services.py:101-133`.
- Celery beat: `backend/app/services/celery_app.py:56-73`. Тело тасков: `backend/app/tasks/_core.py:1937-1951` (паттерн `@celery_app.task(name=...)` + sync-обёртка `_run_coroutine(_async())`).
- Demo-seed + feature: `backend/app/services/demo_bootstrap.py` (medical-seed ~:48-130).

Команда прогона тестов (локально, Win/Py3.13):
```powershell
$env:PYTHONUTF8=1; .\.venv\Scripts\python.exe -m pytest <path> -p no:xdist --timeout=120 -q
```

---

## File Structure

**Новые:**
- `backend/app/domains/shared.py` — `ContingentItemStatus`, `classify` (лифт из medical).
- `backend/app/domains/contractors/__init__.py` — пустой пакет-маркер.
- `backend/app/domains/contractors/lifecycle.py` — `ReadinessStatus`, `EmployeeVerdict`, `evaluate_employee`, `TRAINING_INTERVAL_DAYS`.
- `backend/app/services/contractor_admission.py` — `evaluate_contractor_admission`, `enforce_contractor_admission`, `notify_readiness`.
- `backend/tests/test_domains_shared_classify.py` — app-free юнит лифта.
- `backend/tests/test_contractors_lifecycle.py` — app-free юнит правил вердикта.
- `tests/test_contractor_admission_service.py` — сервис (seeded).
- `tests/api/test_contractors_admission_api.py` — e2e гейта/advisory.
- `tests/test_contractor_readiness_projection.py` — проекция.

**Изменяемые:**
- `backend/app/domains/medical/lifecycle.py` — импорт+ре-экспорт из shared.
- `backend/app/api/routes/contractors.py` — +2 эндпоинта (`admit`, `readiness`) + feature-гейт.
- `backend/app/modules/projections/services.py` — переписать `ContractorReadinessProjectionService.rebuild`.
- `backend/app/services/celery_app.py` — +beat-запись.
- `backend/app/tasks/_core.py` — +таск `contractors.readiness.tick`.
- `backend/app/services/demo_bootstrap.py` — feature `contractors` + seed двух сотрудников.

---

## Task 1: Лифт `classify`/`ContingentItemStatus` в `domains/shared.py`

Рефакторинг без смены поведения: вынести общий хелпер, medical ре-экспортирует.

**Files:**
- Create: `backend/app/domains/shared.py`
- Create: `backend/tests/test_domains_shared_classify.py`
- Modify: `backend/app/domains/medical/lifecycle.py:103-122`

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/test_domains_shared_classify.py
from datetime import date
import pytest
from app.domains.shared import ContingentItemStatus, classify


@pytest.mark.parametrize(
    "valid_until, expected",
    [
        (None, ContingentItemStatus.MISSING),
        (date(2026, 1, 1), ContingentItemStatus.OVERDUE),   # < today
        (date(2026, 6, 20), ContingentItemStatus.DUE_SOON),  # within 30d
        (date(2026, 12, 31), ContingentItemStatus.OK),       # far future
    ],
)
def test_classify_buckets(valid_until, expected):
    assert classify(valid_until, date(2026, 6, 8)) == expected


def test_medical_lifecycle_reexports_shared():
    from app.domains.medical import lifecycle as lc
    assert lc.classify is classify
    assert lc.ContingentItemStatus is ContingentItemStatus
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `... pytest backend/tests/test_domains_shared_classify.py -q`
Expected: FAIL (`ModuleNotFoundError: app.domains.shared`).

- [ ] **Step 3: Создать `domains/shared.py`**

```python
# backend/app/domains/shared.py
"""Domain-neutral readiness helpers shared across bounded contexts.

Lifted from ``domains/medical/lifecycle.py`` so non-medical contours (e.g.
contractors) can reuse deadline classification without importing medical.
"""
from __future__ import annotations

import enum
from datetime import date, timedelta


class ContingentItemStatus(str, enum.Enum):
    """Per-requirement deadline state: ok / due_soon / overdue / missing."""

    OK = "ok"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    MISSING = "missing"


def classify(
    latest_valid_until: date | None, today: date, warning_days: int = 30
) -> ContingentItemStatus:
    """Classify a requirement by its latest valid_until date."""
    if latest_valid_until is None:
        return ContingentItemStatus.MISSING
    if latest_valid_until < today:
        return ContingentItemStatus.OVERDUE
    if latest_valid_until <= today + timedelta(days=warning_days):
        return ContingentItemStatus.DUE_SOON
    return ContingentItemStatus.OK
```

- [ ] **Step 4: Переключить medical на ре-экспорт**

В `backend/app/domains/medical/lifecycle.py` удалить локальные определения `ContingentItemStatus` (строки ~103-109) и `classify` (~112-122), заменив их импортом-ре-экспортом сразу после существующих импортов в начале файла:

```python
# domains/medical/lifecycle.py — заменить локальные ContingentItemStatus/classify
from app.domains.shared import ContingentItemStatus, classify  # re-export (back-compat)
```

Оставить в `lifecycle.py` всё остальное без изменений (`InvalidTransition`, `SuspensionAction`, `interval_for_kind`, `compute_valid_until`, `next_due`, `resolve_required_kinds`, `NormTuple` и т.д.). Убедиться, что `date`/`timedelta`-импорты ещё нужны другим функциям; если `timedelta` больше нигде не используется — удалить из импортов medical, иначе оставить.

- [ ] **Step 5: Запустить тест лифта + регрессию medical**

Run:
```
... pytest backend/tests/test_domains_shared_classify.py -q
... pytest backend/tests/ -k "medical or contingent or lifecycle" -p no:xdist --timeout=120 -q
```
Expected: PASS (лифт зелёный; medical-юниты не сломаны).

- [ ] **Step 6: Commit**

```bash
git add backend/app/domains/shared.py backend/tests/test_domains_shared_classify.py backend/app/domains/medical/lifecycle.py
git commit -m "refactor(domains): lift classify/ContingentItemStatus to domains/shared (medical re-exports)"
```

---

## Task 2: `domains/contractors/lifecycle.py` — правила вердикта (чистые функции)

**Files:**
- Create: `backend/app/domains/contractors/__init__.py`
- Create: `backend/app/domains/contractors/lifecycle.py`
- Create: `backend/tests/test_contractors_lifecycle.py`

- [ ] **Step 1: Написать падающий тест (таблица кейсов)**

```python
# backend/tests/test_contractors_lifecycle.py
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from app.modules.contractors.models import ComplianceStatus
from app.domains.contractors.lifecycle import (
    ReadinessStatus,
    evaluate_employee,
    TRAINING_INTERVAL_DAYS,
)


@dataclass
class _Emp:
    id: str = "e1"
    access_status: ComplianceStatus = ComplianceStatus.VALID
    training_status: ComplianceStatus = ComplianceStatus.VALID
    medical_status: ComplianceStatus = ComplianceStatus.VALID
    last_training_at: datetime | None = None
    next_medical_at: datetime | None = None


TODAY = datetime(2026, 6, 8, tzinfo=timezone.utc).date()


def _dt(d):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def test_all_valid_recent_is_allowed():
    emp = _Emp(
        last_training_at=_dt(TODAY),            # trained today -> deadline far OK
        next_medical_at=_dt(TODAY + timedelta(days=200)),
    )
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.ALLOWED
    assert v.violations == []


def test_stale_valid_medical_is_blocked():
    # medical_status manually 'valid' but deadline is in the past -> BLOCKED
    emp = _Emp(
        last_training_at=_dt(TODAY),
        next_medical_at=_dt(TODAY - timedelta(days=1)),
    )
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.BLOCKED
    assert "medical" in v.violations


def test_expired_status_is_blocked():
    emp = _Emp(access_status=ComplianceStatus.EXPIRED, last_training_at=_dt(TODAY),
               next_medical_at=_dt(TODAY + timedelta(days=200)))
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.BLOCKED
    assert "access" in v.violations


def test_missing_deadlines_are_blocked():
    emp = _Emp(last_training_at=None, next_medical_at=None)
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.BLOCKED
    assert set(v.violations) >= {"training", "medical"}


def test_pending_status_is_warning():
    emp = _Emp(training_status=ComplianceStatus.PENDING, last_training_at=_dt(TODAY),
               next_medical_at=_dt(TODAY + timedelta(days=200)))
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.WARNING
    assert "training" in v.warnings


def test_due_soon_deadline_is_warning():
    emp = _Emp(last_training_at=_dt(TODAY),
               next_medical_at=_dt(TODAY + timedelta(days=10)))  # within 30d window
    v = evaluate_employee(emp, TODAY)
    assert v.status == ReadinessStatus.WARNING
    assert "medical" in v.warnings


def test_training_interval_constant_is_one_year():
    assert TRAINING_INTERVAL_DAYS == 365
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `... pytest backend/tests/test_contractors_lifecycle.py -q`
Expected: FAIL (`ModuleNotFoundError: app.domains.contractors.lifecycle`).

- [ ] **Step 3: Реализовать `lifecycle.py`**

```python
# backend/app/domains/contractors/__init__.py
# (пустой файл — маркер пакета)
```

```python
# backend/app/domains/contractors/lifecycle.py
"""Pure contractor-admission readiness rules (no I/O).

A contractor employee has three requirements — access, training, medical —
each evaluated from a manual status flag cross-checked against a deadline.
The cross-check is the point of this engine: a stale ``valid`` status whose
deadline has passed must NOT count as ready.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.domains.shared import ContingentItemStatus, classify
from app.modules.contractors.models import ComplianceStatus

TRAINING_INTERVAL_DAYS = 365  # срок годности обучения (константа правила, не колонка БД)

_BLOCKING_STATUSES = {ComplianceStatus.EXPIRED, ComplianceStatus.BLOCKED}
_BLOCKING_DEADLINES = {ContingentItemStatus.OVERDUE, ContingentItemStatus.MISSING}
_WARNING_DEADLINES = {ContingentItemStatus.DUE_SOON}


class ReadinessStatus(str, enum.Enum):
    ALLOWED = "allowed"
    WARNING = "warning"
    BLOCKED = "blocked"


@dataclass
class EmployeeVerdict:
    employee_id: str
    status: ReadinessStatus
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _as_date(value: datetime | None) -> date | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


def _assess(requirement: str, status: ComplianceStatus, deadline: ContingentItemStatus | None,
            violations: list[str], warnings: list[str]) -> None:
    """Fold one requirement (status flag + optional deadline) into the verdict lists."""
    blocked = status in _BLOCKING_STATUSES or (deadline in _BLOCKING_DEADLINES)
    if blocked:
        violations.append(requirement)
        return
    if status == ComplianceStatus.PENDING or (deadline in _WARNING_DEADLINES):
        warnings.append(requirement)


def evaluate_employee(emp, today: date) -> EmployeeVerdict:
    """Compute the readiness verdict for a contractor employee."""
    violations: list[str] = []
    warnings: list[str] = []

    # access: status only, no deadline
    _assess("access", emp.access_status, None, violations, warnings)

    # training: deadline = last_training_at + TRAINING_INTERVAL_DAYS
    last_training = _as_date(emp.last_training_at)
    training_deadline = (
        classify(last_training + timedelta(days=TRAINING_INTERVAL_DAYS), today)
        if last_training is not None
        else ContingentItemStatus.MISSING
    )
    _assess("training", emp.training_status, training_deadline, violations, warnings)

    # medical: explicit deadline next_medical_at
    medical_deadline = classify(_as_date(emp.next_medical_at), today)
    _assess("medical", emp.medical_status, medical_deadline, violations, warnings)

    if violations:
        status = ReadinessStatus.BLOCKED
    elif warnings:
        status = ReadinessStatus.WARNING
    else:
        status = ReadinessStatus.ALLOWED
    return EmployeeVerdict(employee_id=emp.id, status=status, violations=violations, warnings=warnings)
```

- [ ] **Step 4: Запустить — убедиться, что зелёный**

Run: `... pytest backend/tests/test_contractors_lifecycle.py -q`
Expected: PASS (все 7 кейсов).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/contractors/__init__.py backend/app/domains/contractors/lifecycle.py backend/tests/test_contractors_lifecycle.py
git commit -m "feat(contractors): pure readiness verdict rules (lifecycle)"
```

---

## Task 3: `services/contractor_admission.py` — evaluate / enforce

**Files:**
- Create: `backend/app/services/contractor_admission.py`
- Create: `tests/test_contractor_admission_service.py`

- [ ] **Step 1: Написать падающий тест (сервис на seeded данных)**

```python
# tests/test_contractor_admission_service.py
import pytest
from datetime import datetime, timezone, timedelta

from app.modules.contractors.models import (
    ComplianceStatus, ContractorRegistry, ContractorEmployee,
)
from app.domains.contractors.lifecycle import ReadinessStatus
from app.services.contractor_admission import (
    evaluate_contractor_admission, enforce_contractor_admission,
)

pytestmark = pytest.mark.asyncio
NOW = datetime.now(timezone.utc)


async def _seed(session, tenant_id="acme"):
    reg = ContractorRegistry(tenant_id=tenant_id, name="Acme Sub")
    session.add(reg)
    await session.flush()
    ready = ContractorEmployee(
        tenant_id=tenant_id, contractor_id=reg.id, full_name="Ready Ivan",
        access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=NOW, next_medical_at=NOW + timedelta(days=200),
    )
    blocked = ContractorEmployee(
        tenant_id=tenant_id, contractor_id=reg.id, full_name="Stale Petr",
        access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,  # stale-valid: deadline in past
        last_training_at=NOW, next_medical_at=NOW - timedelta(days=1),
    )
    session.add_all([ready, blocked])
    await session.commit()
    return reg, ready, blocked


async def test_evaluate_returns_verdicts(async_session):
    reg, ready, blocked = await _seed(async_session)
    employees = [ready, blocked]
    verdicts = {v.employee_id: v for v in evaluate_contractor_admission(
        async_session, tenant_scope=("acme",), employees=employees)}
    assert verdicts[ready.id].status == ReadinessStatus.ALLOWED
    assert verdicts[blocked.id].status == ReadinessStatus.BLOCKED


async def test_enforce_raises_requirements_not_met(async_session):
    reg, ready, blocked = await _seed(async_session)
    with pytest.raises(ValueError) as exc:
        await enforce_contractor_admission(
            async_session, tenant_scope=("acme",), employee_ids=[blocked.id])
    payload = exc.value.args[0]
    assert payload["code"] == "requirements_not_met"
    assert payload["details"][0]["employee_id"] == blocked.id
    assert "medical" in payload["details"][0]["violations"]


async def test_enforce_passes_for_ready(async_session):
    reg, ready, blocked = await _seed(async_session)
    # должно НЕ бросить
    await enforce_contractor_admission(
        async_session, tenant_scope=("acme",), employee_ids=[ready.id])
```

> Примечание: фикстура `async_session` — существующая в репо async-сессия для тестов (см. как её используют medical/projection тесты; имя фикстуры взять из `conftest`). Если у проектных тестов другое имя фикстуры сессии — использовать его.

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `... pytest tests/test_contractor_admission_service.py -q`
Expected: FAIL (`ModuleNotFoundError: app.services.contractor_admission`).

- [ ] **Step 3: Реализовать сервис**

```python
# backend/app/services/contractor_admission.py
"""Contractor-admission guard (mirror of services/person_admission.py).

``evaluate_*`` computes verdicts without raising (read-side / projection).
``enforce_*`` raises ``requirements_not_met`` when any employee is BLOCKED.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contractors import lifecycle as lc
from app.modules.contractors.models import ContractorEmployee


def evaluate_contractor_admission(
    session: AsyncSession,
    *,
    tenant_scope: tuple[str, ...],
    employees: list[ContractorEmployee],
) -> list[lc.EmployeeVerdict]:
    """Pure compute over already-loaded employees (no DB, no raise)."""
    today = datetime.now(timezone.utc).date()
    return [lc.evaluate_employee(emp, today) for emp in employees]


async def _load_employees(
    session: AsyncSession, *, tenant_scope: tuple[str, ...], employee_ids: list[str],
) -> list[ContractorEmployee]:
    if not employee_ids:
        return []
    stmt = select(ContractorEmployee).where(
        ContractorEmployee.id.in_(employee_ids),
        ContractorEmployee.tenant_id.in_(tenant_scope),
        ContractorEmployee.deleted_at.is_(None),
    )
    return list((await session.execute(stmt)).scalars().all())


async def enforce_contractor_admission(
    session: AsyncSession,
    *,
    tenant_scope: tuple[str, ...],
    employee_ids: list[str],
) -> None:
    """Raise ValueError({"code":"requirements_not_met","details":[...]}) if any BLOCKED."""
    employees = await _load_employees(
        session, tenant_scope=tenant_scope, employee_ids=employee_ids)
    verdicts = evaluate_contractor_admission(
        session, tenant_scope=tenant_scope, employees=employees)
    details = [
        {"employee_id": v.employee_id, "violations": v.violations}
        for v in verdicts
        if v.status == lc.ReadinessStatus.BLOCKED
    ]
    if details:
        raise ValueError({"code": "requirements_not_met", "details": details})


async def notify_readiness(
    session: AsyncSession, *, tenant_id: str,
) -> int:
    """Emit readiness outbox events for non-allowed employees of a tenant.

    Returns the number of events enqueued. Idempotency: dedup by
    (employee_id, requirement, status) is handled by the outbox layer key;
    here we enqueue one event per non-allowed employee.
    """
    from app.services.outbox import enqueue_event  # реальный helper — см. ниже

    stmt = select(ContractorEmployee).where(
        ContractorEmployee.tenant_id == tenant_id,
        ContractorEmployee.deleted_at.is_(None),
    )
    employees = list((await session.execute(stmt)).scalars().all())
    verdicts = evaluate_contractor_admission(
        session, tenant_scope=(tenant_id,), employees=employees)
    count = 0
    for v in verdicts:
        if v.status == lc.ReadinessStatus.ALLOWED:
            continue
        event_type = (
            "CONTRACTOR_READINESS_BLOCKED"
            if v.status == lc.ReadinessStatus.BLOCKED
            else "CONTRACTOR_READINESS_WARNING"
        )
        await enqueue_event(
            session,
            tenant_id=tenant_id,
            event_type=event_type,
            payload={
                "employee_id": v.employee_id,
                "violations": v.violations,
                "warnings": v.warnings,
            },
            dedup_key=f"{v.employee_id}:{v.status.value}",
        )
        count += 1
    await session.commit()
    return count
```

> **Реализатору:** `enqueue_event`/`dedup_key` — подставить реальный API outbox-слоя. Найти его так же, как это делает `domains/medical/service.py::notify_overdue` (`grep -n "outbox" backend/app/domains/medical/service.py` и `backend/app/services/`). Если сигнатура иная — адаптировать вызов под неё, сохранив поведение «один dedup-ключ на (employee, status)». Тест на `notify_readiness` добавляется в Task 6 вместе с beat.

- [ ] **Step 4: Запустить — убедиться, что зелёный**

Run: `... pytest tests/test_contractor_admission_service.py -q`
Expected: PASS (3 теста).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/contractor_admission.py tests/test_contractor_admission_service.py
git commit -m "feat(contractors): admission service — evaluate/enforce + readiness notify"
```

---

## Task 4: API — `POST /admit` (гейт) + `GET /readiness` (advisory)

**Files:**
- Modify: `backend/app/api/routes/contractors.py` (после блока employees, ~после :257)
- Create: `tests/api/test_contractors_admission_api.py`

- [ ] **Step 1: Написать падающий e2e-тест**

```python
# tests/api/test_contractors_admission_api.py
import pytest
from datetime import datetime, timezone, timedelta

pytestmark = pytest.mark.asyncio
NOW = datetime.now(timezone.utc)


async def _make_employee(client, headers, *, medical_next):
    reg = (await client.post("/contractors/registry", headers=headers,
                             json={"name": "Acme Sub"})).json()
    emp = (await client.post("/contractors/employees", headers=headers, json={
        "contractor_id": reg["id"], "full_name": "Ivan",
        "access_status": "valid", "training_status": "valid", "medical_status": "valid",
    })).json()
    # выставить дедлайны через PATCH недостаточно (нет полей в Patch) —
    # обновляем напрямую через тестовую сессию ИЛИ через расширенный seed.
    return reg, emp


async def test_admit_blocks_unready(client, writer_headers, db_session):
    # seed сотрудника со stale-valid медосмотром напрямую в БД
    from app.modules.contractors.models import (
        ContractorRegistry, ContractorEmployee, ComplianceStatus)
    reg = ContractorRegistry(tenant_id="acme", name="Acme")
    db_session.add(reg); await db_session.flush()
    emp = ContractorEmployee(
        tenant_id="acme", contractor_id=reg.id, full_name="Stale",
        access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=NOW, next_medical_at=NOW - timedelta(days=1))
    db_session.add(emp); await db_session.commit()

    resp = await client.post(f"/contractors/employees/{emp.id}/admit", headers=writer_headers)
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["code"] == "requirements_not_met"
    assert body["details"][0]["employee_id"] == emp.id


async def test_admit_allows_ready(client, writer_headers, db_session):
    from app.modules.contractors.models import (
        ContractorRegistry, ContractorEmployee, ComplianceStatus)
    reg = ContractorRegistry(tenant_id="acme", name="Acme")
    db_session.add(reg); await db_session.flush()
    emp = ContractorEmployee(
        tenant_id="acme", contractor_id=reg.id, full_name="Ready",
        access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=NOW, next_medical_at=NOW + timedelta(days=200))
    db_session.add(emp); await db_session.commit()

    resp = await client.post(f"/contractors/employees/{emp.id}/admit", headers=writer_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "allowed"

    r2 = await client.get(f"/contractors/employees/{emp.id}/readiness", headers=writer_headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "allowed"
```

> Имена фикстур (`client`, `writer_headers`, `db_session`) взять из существующих API-тестов контура (см. `tests/api/` соседние файлы; например как тестируется `contractors` или `medical` API). Привести в соответствие.

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `... pytest tests/api/test_contractors_admission_api.py -q`
Expected: FAIL (404 — эндпоинтов ещё нет).

- [ ] **Step 3: Добавить эндпоинты в `contractors.py`**

В импорты файла добавить:
```python
from fastapi import HTTPException  # уже импортирован; убедиться
from app.core.feature_flags import is_feature_enabled
from app.services.contractor_admission import (
    enforce_contractor_admission, evaluate_contractor_admission,
)
```

Добавить хелпер фичефлага и helper загрузки одного сотрудника (рядом с прочими), затем два эндпоинта после `patch_contractor_employee` (после :257):

```python
_CONTRACTOR_FEATURE_CODE = "contractors"


async def require_contractors_feature(tenant: TenantDep, session: SessionDep) -> None:
    if not await is_feature_enabled(session, str(tenant.id), _CONTRACTOR_FEATURE_CODE):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Contractors feature is not enabled for this tenant")


async def _fetch_employee(session: AsyncSession, tenant: Tenant, employee_id: str) -> ContractorEmployee:
    row = (
        await session.execute(
            select(ContractorEmployee).where(
                ContractorEmployee.id == employee_id,
                ContractorEmployee.tenant_id == str(tenant.id),
                ContractorEmployee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found")
    return row


def _verdict_body(verdict) -> dict:
    return {
        "employee_id": verdict.employee_id,
        "status": verdict.status.value,
        "violations": verdict.violations,
        "warnings": verdict.warnings,
    }


@router.get("/employees/{employee_id}/readiness")
async def contractor_employee_readiness(
    employee_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess,
    _feature: None = Depends(require_contractors_feature),
):
    row = await _fetch_employee(session, tenant, employee_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="read contractors")
    verdict = evaluate_contractor_admission(
        session, tenant_scope=(str(tenant.id),), employees=[row])[0]
    return _verdict_body(verdict)


@router.post("/employees/{employee_id}/admit")
async def admit_contractor_employee(
    employee_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess,
    _feature: None = Depends(require_contractors_feature),
):
    row = await _fetch_employee(session, tenant, employee_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="manage contractors")
    try:
        await enforce_contractor_admission(
            session, tenant_scope=(str(tenant.id),), employee_ids=[employee_id])
    except ValueError as exc:
        payload = exc.args[0] if exc.args else {}
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "requirements_not_met",
                "error_code": "requirements_not_met",
                "message": "Contractor employee is not cleared for admission",
                "type": "contractors",
                "details": payload.get("details", []) if isinstance(payload, dict) else [],
            },
        ) from exc
    verdict = evaluate_contractor_admission(
        session, tenant_scope=(str(tenant.id),), employees=[row])[0]
    return _verdict_body(verdict)
```

> Аудит-запись (`AuditService` событие `contractor_admission_granted`) — добавить по образцу других write-эндпоинтов medical (если в контуре contractors аудит ещё не подключён — пропустить в Срезе-1, чтобы не расширять объём; отметить в отчёте).

- [ ] **Step 4: Запустить — убедиться, что зелёный**

Run: `... pytest tests/api/test_contractors_admission_api.py -q`
Expected: PASS (3 проверки: 409 для неготового, 200+allowed, readiness advisory).

> Если тест падает на feature-гейте (404 «not enabled») — в тестовой среде включить фичу `contractors` (через тот же механизм, что medical-тесты включают `medical`; обычно seed/фикстура). Согласовать с Task 7.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/contractors.py tests/api/test_contractors_admission_api.py
git commit -m "feat(contractors): admission gate (admit 409) + advisory readiness endpoints"
```

---

## Task 5: Переписать проекцию `ContractorReadinessProjectionService.rebuild`

**Files:**
- Modify: `backend/app/modules/projections/services.py:101-133`
- Create: `tests/test_contractor_readiness_projection.py`

- [ ] **Step 1: Написать падающий тест**

```python
# tests/test_contractor_readiness_projection.py
import pytest
from datetime import datetime, timezone, timedelta

from app.modules.contractors.models import (
    ContractorRegistry, ContractorEmployee, ComplianceStatus)
from app.modules.projections.models import ContractorReadinessReadModel
from app.modules.projections.services import ContractorReadinessProjectionService
from sqlalchemy import select

pytestmark = pytest.mark.asyncio
NOW = datetime.now(timezone.utc)


async def test_rebuild_fills_real_counts(async_session):
    reg = ContractorRegistry(tenant_id="acme", name="Acme")
    async_session.add(reg); await async_session.flush()
    async_session.add_all([
        ContractorEmployee(tenant_id="acme", contractor_id=reg.id, full_name="Ready",
            access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
            medical_status=ComplianceStatus.VALID,
            last_training_at=NOW, next_medical_at=NOW + timedelta(days=200)),
        ContractorEmployee(tenant_id="acme", contractor_id=reg.id, full_name="Blocked",
            access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
            medical_status=ComplianceStatus.VALID,
            last_training_at=NOW, next_medical_at=NOW - timedelta(days=1)),
    ])
    await async_session.commit()

    total = await ContractorReadinessProjectionService(async_session, "acme").rebuild()
    assert total >= 1

    row = (await async_session.execute(select(ContractorReadinessReadModel).where(
        ContractorReadinessReadModel.tenant_id == "acme",
        ContractorReadinessReadModel.contractor_id == reg.id))).scalar_one()
    assert row.workers_total == 2
    assert row.workers_ready == 1
    assert row.workers_blocked == 1
    assert row.overdue_items_count >= 1
    assert row.readiness_status == "blocked"
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `... pytest tests/test_contractor_readiness_projection.py -q`
Expected: FAIL (`workers_total == 0`, `readiness_status == "unknown"` — заглушка не наполняет).

- [ ] **Step 3: Переписать `rebuild`**

Заменить тело `ContractorReadinessProjectionService.rebuild` (строки 106-133) на:

```python
    async def rebuild(self) -> int:
        from app.domains.contractors.lifecycle import ContingentItemStatus  # noqa: F401
        from app.domains.contractors.lifecycle import ReadinessStatus, evaluate_employee
        from app.domains.shared import ContingentItemStatus as _DL
        from datetime import datetime, timezone, timedelta
        from app.domains.contractors.lifecycle import TRAINING_INTERVAL_DAYS
        from app.domains.shared import classify as _classify

        today = datetime.now(timezone.utc).date()

        # active package counts (preserve existing behaviour)
        pkg_rows = (await self.session.execute(
            select(ClientPackageRun).where(ClientPackageRun.tenant_id == self.tenant_id)
        )).scalars().all()
        packages_by_contractor: dict[str, int] = {}
        for run in pkg_rows:
            cid = run.client_company_id
            if cid:
                packages_by_contractor[cid] = packages_by_contractor.get(cid, 0) + 1

        # contractor employees grouped by contractor
        emp_rows = (await self.session.execute(
            select(ContractorEmployee).where(
                ContractorEmployee.tenant_id == self.tenant_id,
                ContractorEmployee.deleted_at.is_(None),
            )
        )).scalars().all()
        by_contractor: dict[str, list] = {}
        for emp in emp_rows:
            by_contractor.setdefault(emp.contractor_id, []).append(emp)

        contractor_ids = set(by_contractor) | set(packages_by_contractor)
        total = 0
        for contractor_id in contractor_ids:
            employees = by_contractor.get(contractor_id, [])
            verdicts = [evaluate_employee(e, today) for e in employees]
            workers_total = len(verdicts)
            workers_ready = sum(1 for v in verdicts if v.status == ReadinessStatus.ALLOWED)
            workers_blocked = sum(1 for v in verdicts if v.status == ReadinessStatus.BLOCKED)
            overdue_items = sum(len(v.violations) for v in verdicts)
            missing_training = sum(1 for v in verdicts if "training" in v.violations)
            if workers_blocked:
                readiness = "blocked"
            elif any(v.status == ReadinessStatus.WARNING for v in verdicts):
                readiness = "warning"
            elif workers_total:
                readiness = "ready"
            else:
                readiness = "unknown"

            row = (await self.session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == self.tenant_id,
                    ContractorReadinessReadModel.contractor_id == contractor_id,
                )
            )).scalar_one_or_none()
            if row is None:
                row = ContractorReadinessReadModel(
                    tenant_id=self.tenant_id, contractor_id=contractor_id)
                self.session.add(row)
            row.readiness_status = readiness
            row.workers_total = workers_total
            row.workers_ready = workers_ready
            row.workers_blocked = workers_blocked
            row.missing_training_count = missing_training
            row.overdue_items_count = overdue_items
            row.active_packages_count = packages_by_contractor.get(contractor_id, 0)
            total += 1

        await self.session.commit()
        return total
```

Убедиться, что в начале `services.py` есть импорт `ContractorEmployee` (добавить `from app.modules.contractors.models import ContractorEmployee`, если отсутствует). Убрать неиспользуемые локальные импорты (`_DL`, `_classify`, `TRAINING_INTERVAL_DAYS`, `ContingentItemStatus`) — оставить только реально используемые `ReadinessStatus`, `evaluate_employee` (они вынесены в начало метода для наглядности; при желании поднять в начало модуля).

- [ ] **Step 4: Запустить — убедиться, что зелёный + регрессия проекций**

Run:
```
... pytest tests/test_contractor_readiness_projection.py -q
... pytest tests/ backend/tests/ -k "projection" -p no:xdist --timeout=120 -q
```
Expected: PASS (новый тест + существующие projection-тесты не сломаны).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/projections/services.py tests/test_contractor_readiness_projection.py
git commit -m "feat(contractors): real readiness projection (fill read-model from verdicts)"
```

---

## Task 6: Beat-таск `contractors.readiness.tick`

**Files:**
- Modify: `backend/app/services/celery_app.py:56-73`
- Modify: `backend/app/tasks/_core.py` (рядом с `medical_contingent_tick` ~:1937-1951)
- Modify: `tests/test_contractor_admission_service.py` (добавить тест `notify_readiness`)

- [ ] **Step 1: Тест на `notify_readiness`**

Добавить в `tests/test_contractor_admission_service.py`:

```python
async def test_notify_readiness_enqueues_for_non_allowed(async_session):
    from app.services.contractor_admission import notify_readiness
    reg, ready, blocked = await _seed(async_session)
    count = await notify_readiness(async_session, tenant_id="acme")
    assert count == 1  # только blocked сотрудник
```

- [ ] **Step 2: Запустить — падает (или зелёный, если outbox-API уже совпал)**

Run: `... pytest tests/test_contractor_admission_service.py::test_notify_readiness_enqueues_for_non_allowed -q`
Expected: FAIL (если в Task 3 `enqueue_event` оставлен как заглушка-импорт). Привести `notify_readiness` в соответствие с реальным outbox-API (см. примечание в Task 3) до прохождения.

- [ ] **Step 3: Добавить таск в `_core.py`**

По образцу `medical_contingent_tick` (`_core.py:1937-1951`):

```python
@celery_app.task(
    name="contractors.readiness.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def contractors_readiness_tick() -> int:
    return _run_coroutine(_contractors_readiness_tick())


async def _contractors_readiness_tick() -> int:
    from app.services.contractor_admission import notify_readiness
    from app.modules.projections.services import ContractorReadinessProjectionService

    total = 0
    async with _session_scope() as session:  # тот же helper сессии, что и в _medical_contingent_tick
        tenant_ids = await _all_tenant_ids(session)  # как в medical tick
        for tenant_id in tenant_ids:
            await ContractorReadinessProjectionService(session, tenant_id).rebuild()
            total += await notify_readiness(session, tenant_id=tenant_id)
    return total
```

> **Реализатору:** точные имена helper'ов сессии (`_session_scope`) и перечисления тенантов (`_all_tenant_ids`) взять из тела `_medical_contingent_tick` (`_core.py:1948+`) — использовать те же, что там. Не выдумывать новые.

- [ ] **Step 4: Добавить запись в beat-расписание**

В `backend/app/services/celery_app.py` в `beat_schedule` (после `medical-contingent-daily`):

```python
    "contractors-readiness-daily": {
        "task": "contractors.readiness.tick",
        "schedule": crontab(hour=3, minute=30),
    },
```

- [ ] **Step 5: Запустить тест + smoke-импорт таск-модуля**

Run:
```
... pytest tests/test_contractor_admission_service.py -q
... .\.venv\Scripts\python.exe -c "import app.tasks._core"
```
Expected: PASS + импорт без ошибок (таск зарегистрирован).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/celery_app.py backend/app/tasks/_core.py tests/test_contractor_admission_service.py
git commit -m "feat(contractors): daily readiness beat tick + outbox notifications"
```

---

## Task 7: Feature-flag `contractors` + demo-seed

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py` (рядом с medical-seed ~:48-130)

- [ ] **Step 1: Тест на seed/feature**

Добавить (или в существующий demo-bootstrap-тест) проверку:

```python
# tests/test_demo_bootstrap_contractors.py
import pytest
from sqlalchemy import select
from app.modules.contractors.models import ContractorEmployee
from app.core.feature_flags import is_feature_enabled

pytestmark = pytest.mark.asyncio


async def test_bootstrap_seeds_contractors_feature_and_employees(async_session, demo_tenant_id):
    # demo_bootstrap уже выполнен фикстурой/в тесте; имена взять из существующего demo-bootstrap теста
    assert await is_feature_enabled(async_session, demo_tenant_id, "contractors")
    emps = (await async_session.execute(select(ContractorEmployee).where(
        ContractorEmployee.tenant_id == demo_tenant_id))).scalars().all()
    assert len(emps) >= 2  # один готовый, один просроченный
```

> Имена фикстур (`demo_tenant_id`, способ запуска bootstrap) взять из существующего теста demo_bootstrap (см. `grep -rn "demo_bootstrap" tests/`).

- [ ] **Step 2: Запустить — убедиться, что падает**

Run: `... pytest tests/test_demo_bootstrap_contractors.py -q`
Expected: FAIL (фича/сотрудники ещё не сидируются).

- [ ] **Step 3: Добавить seed в `demo_bootstrap.py`**

По образцу medical-seed (Feature code="medical"):

```python
        # Feature-flag: contractors (default-on), idempotent.
        await _ensure_feature(session, tenant_id, code="contractors", title="Подрядчики")
        # ↑ использовать тот же helper, которым сидируется medical-фича;
        #   если helper'а нет — повторить inline-паттерн medical (select-or-create Feature).

        # Демо-подрядчик с двумя сотрудниками: готовый + просроченный медосмотр.
        from app.modules.contractors.models import (
            ContractorRegistry, ContractorEmployee, ComplianceStatus)
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        existing_reg = (await session.execute(
            select(ContractorRegistry).where(
                ContractorRegistry.tenant_id == tenant_id,
                ContractorRegistry.name == "Демо-подрядчик"))).scalar_one_or_none()
        if existing_reg is None:
            reg = ContractorRegistry(tenant_id=tenant_id, name="Демо-подрядчик", status="active")
            session.add(reg); await session.flush()
            session.add_all([
                ContractorEmployee(
                    tenant_id=tenant_id, contractor_id=reg.id, full_name="Готовый Иван",
                    access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
                    medical_status=ComplianceStatus.VALID,
                    last_training_at=now, next_medical_at=now + timedelta(days=200)),
                ContractorEmployee(
                    tenant_id=tenant_id, contractor_id=reg.id, full_name="Просроченный Пётр",
                    access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
                    medical_status=ComplianceStatus.VALID,
                    last_training_at=now, next_medical_at=now - timedelta(days=1)),
            ])
            await session.commit()
```

> Точное имя helper'а фичи (`_ensure_feature`) и место вставки — согласовать с тем, как сидируется medical-фича в этом файле. Сохранить идемпотентность (повторный bootstrap не дублирует).

- [ ] **Step 4: Запустить — зелёный + регрессия bootstrap**

Run:
```
... pytest tests/test_demo_bootstrap_contractors.py -q
... pytest tests/ -k "demo_bootstrap or bootstrap" -p no:xdist --timeout=120 -q
```
Expected: PASS (новый тест + bootstrap-регрессия зелёная, повторный запуск идемпотентен).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demo_bootstrap.py tests/test_demo_bootstrap_contractors.py
git commit -m "feat(contractors): seed contractors feature-flag + demo employees"
```

---

## Task 8: Регрессии + holistic-review

**Files:** нет новых; верификация.

- [ ] **Step 1: Прогнать весь контурный + затронутый когорт**

Run:
```
... pytest backend/tests/test_domains_shared_classify.py backend/tests/test_contractors_lifecycle.py tests/test_contractor_admission_service.py tests/api/test_contractors_admission_api.py tests/test_contractor_readiness_projection.py tests/test_demo_bootstrap_contractors.py -p no:xdist --timeout=180 -q
```
Expected: all PASS.

- [ ] **Step 2: Регрессия смежного (medical/projection/mapper)**

Run:
```
... pytest backend/tests/ tests/ -k "medical or projection or mapper or contingent or bootstrap" -p no:xdist --timeout=300 -q
```
Expected: PASS (лифт `classify` и новый домен ничего не сломали).

- [ ] **Step 3: Holistic-review (requesting-code-review skill)**

Запросить ревью всей ветки против спека `docs/superpowers/specs/2026-06-08-contractors-admission-design.md`: правила вердикта, контракт ошибки (409), наполнение read-модели, идемпотентность beat, отсутствие миграции. Зафиксировать вердикт.

- [ ] **Step 4: Обновить handoff-отчёт**

В `AI_IMPLEMENTATION_REPORT.md` добавить top-handoff: контур B.14 «Подрядчики» Срез-1 (движок допуска) построен; перечислить файлы/тесты/решения (409-гейт, лифт classify, проекция наполнена, миграции нет); Next = влить ветку (решение пользователя) + Срез-2 (документы/посетители/FSM-запись/интеграция доменов). Обновить память [[tz-section-b-ground-truth]].

- [ ] **Step 5: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(report): Подрядчики Срез-1 (движок допуска) — handoff"
```

---

## Self-Review (выполнено автором плана)

- **Покрытие спека:** §3 архитектура → Tasks 1-3; §4 правила → Task 2; §5 гейт → Task 4 (409, не 422 — поправка по конвенции packs.py); §6 проекция → Task 5; §7 beat → Task 6; §8 feature/seed → Task 7; §10 тесты → в каждой задаче; §11 манифест → File Structure. Гэпов нет.
- **Плейсхолдеры:** реализатору оставлены 3 явных «подставить реальное имя» точки (outbox-API в Task 3/6, имена тестовых фикстур, helper фичи/сессии) — это интеграция с существующим кодом, имена которого зависят от репо; каждая снабжена точным указанием, где взять (`grep`/file:line). Это не «TODO позже», а адресные привязки.
- **Согласованность типов:** `EmployeeVerdict`/`ReadinessStatus`/`evaluate_employee` определены в Task 2 и используются единообразно в Tasks 3/5/6; `evaluate_contractor_admission`/`enforce_contractor_admission`/`notify_readiness` — Task 3, используются в Tasks 4/6. Контракт ошибки `{code,error_code,message,type,details}` — Task 4, зеркало packs.py.
- **Поправка к спеку:** код ошибки гейта **409 CONFLICT** (а не 422) — приведено в соответствие с `packs.py:316`. Спек §5 говорил 422; реализатор следует плану (409).
