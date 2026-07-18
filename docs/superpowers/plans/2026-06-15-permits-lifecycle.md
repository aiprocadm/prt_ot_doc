# Личные допуски (Permit): запись + жизненный цикл — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Превратить тонкую read-only модель `Permit` в управляемую сущность: чистый FSM, конверсия статуса native-enum→VARCHAR, сервис (create/update/extend/revoke/expire), CRUD-API `/permits`, ежедневный beat авто-просрочки.

**Architecture:** Зеркалит срез СИЗ (`domains/ppe`): чистый `domains/permits/lifecycle.py` (FSM без I/O) → session-aware `domains/permits/service.py` → роуты `api/routes/permits.py`. Статус `permit.status` переводится из `Enum(PermitStatus)` в `VARCHAR(32)` (анти-грабли, как `ppeissue.status` в `sz01`); читатели статуса адаптируются на строковое значение. Формальный наряд-допуск §16 — отдельный Срез-2, вне этого плана.

**Tech Stack:** Python 3.12 (CI; локально Py3.13/.venv), FastAPI, SQLAlchemy 2.0 async, Alembic, Celery beat, pytest. Спека: `docs/superpowers/specs/2026-06-15-permits-lifecycle-design.md`.

**Ветка:** `feat/permits-lifecycle` (спека уже закоммичена там).

**Локальный прогон тестов (Win/Py3.13/.venv):** через PowerShell с редиректом в файл (см. [[py313_win_pytest_invocation]]):
`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest <путь> -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"` — затем читать `_t.txt`. Канон Py3.12 = CI; расхождение версии указывать, не абортить.

---

## File Structure

**Создать:**
- `backend/app/domains/permits/__init__.py` — реэкспорт публичных функций/констант.
- `backend/app/domains/permits/lifecycle.py` — чистый FSM + статусы + `is_expired`/`due_status`.
- `backend/app/domains/permits/service.py` — session-aware операции.
- `backend/app/schemas/permit.py` — Pydantic-схемы.
- `backend/app/api/routes/permits.py` — CRUD + extend/revoke.
- `backend/app/migrations/versions/20260615_prm01_permit_status_varchar.py` — конверсия статуса.
- `backend/tests/test_permit_lifecycle.py` — unit FSM (app-free → `backend/tests/`).
- `backend/tests/test_prm01_permit_status_migration.py` — guard миграции (app-free).
- `tests/test_permit_service.py` — сервис (нужны БД-фикстуры → корневой `tests/`).
- `tests/api/test_permits_api.py` — CRUD + операции + ABAC.
- `tests/test_permits_expire_tick.py` — beat авто-просрочки.

**Изменить:**
- `backend/app/models/models.py:1421` — тип колонки `Permit.status` → `String(32)`.
- `backend/app/api/v1/route_groups.py` — импорт + регистрация `permits.router`.
- `backend/app/services/employee_card.py` — сравнения `PermitStatus.ACTIVE` → `.value`.
- `backend/app/modules/data_quality/rules.py:358` — `PermitStatus.ACTIVE` → `.value`.
- `backend/app/domains/training/service.py:261` — `PermitStatus.ACTIVE/EXPIRED` → `.value`.
- `backend/app/tasks/_core.py` — задача `permits.expiry.tick`.
- `backend/app/services/celery_app.py` — beat-расписание `permits-expiry-daily`.

> **Размещение тестов:** чистые тесты (lifecycle, guard миграции) идут в `backend/tests/` (без БД). Тесты, которым нужны `sessionmaker`/`async_client`/`data_factory`/`make_auth_headers`, идут в корневой `tests/` — фикстуры объявлены в `tests/conftest.py`. Фабрика: `data_factory.create_person()` создаёт tenant+company+person (поля `first_name`/`last_name`, `tenant_slug="test"`); `make_auth_headers(RoleEnum.ADMIN)` аутентифицирует под тенант `test`. Калибровать сигнатуры по `tests/api/test_ppe_norms_api.py` и `tests/utils/factories.py`.

---

## Task 1: Чистый lifecycle-модуль (FSM + статусы)

**Files:**
- Create: `backend/app/domains/permits/lifecycle.py`
- Create: `backend/app/domains/permits/__init__.py`
- Test: `backend/tests/test_permit_lifecycle.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_permit_lifecycle.py
from datetime import date

import pytest

from app.domains.permits import lifecycle as lc


def test_status_constants_are_lowercase_values():
    assert lc.PERMIT_STATUS_ACTIVE == "active"
    assert lc.PERMIT_STATUS_EXPIRED == "expired"
    assert lc.PERMIT_STATUS_REVOKED == "revoked"
    assert lc.PERMIT_STATUSES == frozenset({"active", "expired", "revoked"})


def test_allowed_transitions():
    lc.validate_transition(lc.PERMIT_STATUS_ACTIVE, lc.PERMIT_STATUS_EXPIRED)
    lc.validate_transition(lc.PERMIT_STATUS_ACTIVE, lc.PERMIT_STATUS_REVOKED)
    lc.validate_transition(lc.PERMIT_STATUS_EXPIRED, lc.PERMIT_STATUS_ACTIVE)  # re-validation


def test_forbidden_transitions_raise():
    with pytest.raises(lc.PermitTransitionError):
        lc.validate_transition(lc.PERMIT_STATUS_REVOKED, lc.PERMIT_STATUS_ACTIVE)
    with pytest.raises(lc.PermitTransitionError):
        lc.validate_transition(lc.PERMIT_STATUS_EXPIRED, lc.PERMIT_STATUS_REVOKED)


def test_is_expired():
    today = date(2026, 6, 15)
    assert lc.is_expired("active", date(2026, 6, 14), today) is True
    assert lc.is_expired("active", date(2026, 6, 15), today) is False  # not yet < today
    assert lc.is_expired("active", None, today) is False               # termless
    assert lc.is_expired("revoked", date(2026, 1, 1), today) is False  # only active expires


def test_due_status():
    today = date(2026, 6, 15)
    assert lc.due_status("active", date(2026, 6, 1), today) == "expired"
    assert lc.due_status("active", date(2026, 12, 1), today) == "active"
    assert lc.due_status("revoked", date(2026, 1, 1), today) == "revoked"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_permit_lifecycle.py -p no:xdist --timeout=120 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domains.permits'`.

- [ ] **Step 3: Write the lifecycle module**

```python
# backend/app/domains/permits/lifecycle.py
"""Pure personal-permit (личный допуск) lifecycle rules: FSM + expiry helpers.

No I/O and no sqlalchemy imports — mirrors ``domains/ppe/lifecycle.py``.
Status values are the canonical VARCHAR values stored in ``permit.status``
(lowercase, see migration prm01).
"""
from __future__ import annotations

from datetime import date

PERMIT_STATUS_ACTIVE = "active"
PERMIT_STATUS_EXPIRED = "expired"
PERMIT_STATUS_REVOKED = "revoked"

PERMIT_STATUSES = frozenset({
    PERMIT_STATUS_ACTIVE,
    PERMIT_STATUS_EXPIRED,
    PERMIT_STATUS_REVOKED,
})

# active may expire (by date) or be revoked (manually); an expired permit may be
# re-validated to active via extension; revoked is terminal.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    PERMIT_STATUS_ACTIVE: frozenset({PERMIT_STATUS_EXPIRED, PERMIT_STATUS_REVOKED}),
    PERMIT_STATUS_EXPIRED: frozenset({PERMIT_STATUS_ACTIVE}),
    PERMIT_STATUS_REVOKED: frozenset(),
}


class PermitTransitionError(ValueError):
    """Invalid permit status transition (maps to HTTP 409 at the API layer)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid permit transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    """Raise PermitTransitionError unless current -> target is allowed."""
    allowed = ALLOWED_TRANSITIONS.get(current)
    if allowed is None or target not in allowed:
        raise PermitTransitionError(current, target)


def is_expired(status: str, valid_until: date | None, today: date) -> bool:
    """True when an active permit is past its valid_until date."""
    return (
        status == PERMIT_STATUS_ACTIVE
        and valid_until is not None
        and valid_until < today
    )


def due_status(status: str, valid_until: date | None, today: date) -> str:
    """Target status after applying date-driven expiry (no manual transitions)."""
    if is_expired(status, valid_until, today):
        return PERMIT_STATUS_EXPIRED
    return status
```

```python
# backend/app/domains/permits/__init__.py
"""Domain logic for personal permits (личные допуски)."""

from app.domains.permits.lifecycle import (
    ALLOWED_TRANSITIONS,
    PERMIT_STATUS_ACTIVE,
    PERMIT_STATUS_EXPIRED,
    PERMIT_STATUS_REVOKED,
    PERMIT_STATUSES,
    PermitTransitionError,
    due_status,
    is_expired,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS",
    "PERMIT_STATUS_ACTIVE",
    "PERMIT_STATUS_EXPIRED",
    "PERMIT_STATUS_REVOKED",
    "PERMIT_STATUSES",
    "PermitTransitionError",
    "due_status",
    "is_expired",
    "validate_transition",
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_permit_lifecycle.py -p no:xdist --timeout=120 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/permits/ backend/tests/test_permit_lifecycle.py
git commit -m "feat(permits): pure lifecycle FSM + expiry helpers (Срез-1)"
```

---

## Task 2: Конверсия статуса в VARCHAR + миграция prm01 + адаптация читателей

**Files:**
- Modify: `backend/app/models/models.py:1421`
- Create: `backend/app/migrations/versions/20260615_prm01_permit_status_varchar.py`
- Modify: `backend/app/services/employee_card.py` (3 сравнения)
- Modify: `backend/app/modules/data_quality/rules.py:358`
- Modify: `backend/app/domains/training/service.py:261`
- Test: `backend/tests/test_prm01_permit_status_migration.py`

- [ ] **Step 1: Write the failing migration-guard test**

```python
# backend/tests/test_prm01_permit_status_migration.py
"""prm01 migration + model shape: Permit.status is VARCHAR(32), not native enum.

Mirrors backend/tests/test_sz01_ppe_766n_migration.py — reads the migration file
as text (its module name starts with a digit, so it can't be imported normally).
"""
from __future__ import annotations

import re
from pathlib import Path

from app.models.models import Permit, PermitStatus

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260615_prm01_permit_status_varchar.py"
)


def test_permit_status_is_varchar_not_native_enum():
    col = Permit.__table__.c["status"]
    assert type(col.type).__name__ == "String"
    assert col.type.length == 32


def test_permit_status_enum_values_lowercase():
    assert {m.value for m in PermitStatus} == {"active", "expired", "revoked"}


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260615_prm01_permit_status_varchar"' in src
    assert 'down_revision = "20260614_drift01_orm_pg_column_closure"' in src


def test_migration_converts_status_and_drops_enum_type():
    src = MIGRATION.read_text(encoding="utf-8")
    assert "VARCHAR(32)" in src
    assert re.search(r"USING\s+lower\(status::text\)", src)
    assert "DROP TYPE IF EXISTS permitstatus" in src
    assert re.search(r"USING\s+upper\(status\)", src)  # downgrade restores enum NAME labels
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_prm01_permit_status_migration.py -p no:xdist --timeout=120 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: FAIL — `FileNotFoundError`/`AssertionError` (migration not created; status still native enum).

- [ ] **Step 3: Change the model column type**

In `backend/app/models/models.py`, replace line 1421:

```python
    status: Mapped[PermitStatus] = mapped_column(Enum(PermitStatus), nullable=False, default=PermitStatus.ACTIVE)
```

with:

```python
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=PermitStatus.ACTIVE.value)
```

Leave the `PermitStatus` enum class (lines 1407-1410) in place — it stays the source of the canonical string values (`.value`) and keeps existing imports working. `String` and `Enum` are already imported in this module.

- [ ] **Step 4: Write the migration**

```python
# backend/app/migrations/versions/20260615_prm01_permit_status_varchar.py
"""prm01: personal permit status native enum -> VARCHAR(32), lowercase.

In-place type conversion mirroring sz01 (ppeissue.status). The legacy enum
``permitstatus`` already covers all three values (active/expired/revoked),
so downgrade is fully reversible — no data blocker is needed.
"""
from __future__ import annotations

from alembic import op

revision = "20260615_prm01_permit_status_varchar"
down_revision = "20260614_drift01_orm_pg_column_closure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute(
            "ALTER TABLE permit ALTER COLUMN status TYPE VARCHAR(32) "
            "USING lower(status::text)"
        )
        op.execute("ALTER TABLE permit ALTER COLUMN status SET DEFAULT 'active'")
        op.execute("DROP TYPE IF EXISTS permitstatus")
    else:
        # SQLite stores Enum as VARCHAR and does not enforce length — just normalise case.
        op.execute("UPDATE permit SET status = lower(status)")


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        op.execute("ALTER TABLE permit ALTER COLUMN status DROP DEFAULT")
        op.execute("CREATE TYPE permitstatus AS ENUM ('ACTIVE', 'EXPIRED', 'REVOKED')")
        op.execute(
            "ALTER TABLE permit ALTER COLUMN status TYPE permitstatus "
            "USING upper(status)::permitstatus"
        )
        op.execute("ALTER TABLE permit ALTER COLUMN status SET DEFAULT 'ACTIVE'")
    else:
        op.execute("UPDATE permit SET status = upper(status)")
```

- [ ] **Step 5: Adapt the status readers to the string value**

In `backend/app/modules/data_quality/rules.py` line 358, change:

```python
                Permit.status == PermitStatus.ACTIVE,
```
to:
```python
                Permit.status == PermitStatus.ACTIVE.value,
```

In `backend/app/domains/training/service.py` line 261, change:

```python
            status=PermitStatus.ACTIVE if (valid_until is None or valid_until >= computed_issued_at) else PermitStatus.EXPIRED,
```
to:
```python
            status=PermitStatus.ACTIVE.value if (valid_until is None or valid_until >= computed_issued_at) else PermitStatus.EXPIRED.value,
```

In `backend/app/services/employee_card.py`, append `.value` to the three `PermitStatus.ACTIVE` comparisons inside `_build_permits` (one Python-level `permit.status == PermitStatus.ACTIVE`, two `Permit.status == PermitStatus.ACTIVE` count queries). Each becomes `PermitStatus.ACTIVE.value`.

Then check `EmployeePermitItem.status` in `backend/app/schemas/employee.py` — it must be typed `str` (it receives `permit.status`, now a plain string). If it is typed `PermitStatus`, change it to `str`. The calendar aggregator already reads status defensively (`permit.status.value if hasattr(permit.status, "value") else str(permit.status)`) — no change needed there.

- [ ] **Step 6: Run the migration-guard test + reader regression**

Run:
```
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_prm01_permit_status_migration.py tests/test_employee_card.py tests/test_data_quality.py -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"
```
Expected: PASS. (Reader test files confirmed present: `tests/test_employee_card.py`, `tests/test_data_quality.py`.) Note any Py3.12-vs-3.13 mismatch; do not abort.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/models.py backend/app/migrations/versions/20260615_prm01_permit_status_varchar.py backend/app/services/employee_card.py backend/app/modules/data_quality/rules.py backend/app/domains/training/service.py backend/tests/test_prm01_permit_status_migration.py
git commit -m "feat(permits): convert status native-enum -> VARCHAR (prm01) + adapt readers"
```

---

## Task 3: Сервис (create/update/extend/revoke/expire_due)

**Files:**
- Create: `backend/app/domains/permits/service.py`
- Modify: `backend/app/domains/permits/__init__.py` (реэкспорт сервиса)
- Test: `tests/test_permit_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_permit_service.py
from datetime import date, timedelta

import pytest

from app.domains.permits import lifecycle as lc
from app.domains.permits import service as svc


@pytest.mark.asyncio
async def test_create_then_revoke(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="Работа на высоте", issued_at=date.today(),
            valid_until=date.today() + timedelta(days=30), position_id=None,
        )
        assert permit.status == lc.PERMIT_STATUS_ACTIVE

        revoked = await svc.revoke_permit(session, tenant_id=person.tenant_id, permit_id=permit.id)
        assert revoked.status == lc.PERMIT_STATUS_REVOKED

        with pytest.raises(lc.PermitTransitionError):  # revoked is terminal
            await svc.revoke_permit(session, tenant_id=person.tenant_id, permit_id=permit.id)


@pytest.mark.asyncio
async def test_create_already_expired_is_expired(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="Огневые работы", issued_at=date.today() - timedelta(days=10),
            valid_until=date.today() - timedelta(days=1), position_id=None,
        )
        assert permit.status == lc.PERMIT_STATUS_EXPIRED


@pytest.mark.asyncio
async def test_extend_revalidates_expired(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="Газоопасные работы", issued_at=date.today() - timedelta(days=10),
            valid_until=date.today() - timedelta(days=1), position_id=None,
        )
        assert permit.status == lc.PERMIT_STATUS_EXPIRED
        extended = await svc.extend_permit(
            session, tenant_id=person.tenant_id, permit_id=permit.id,
            valid_until=date.today() + timedelta(days=60),
        )
        assert extended.status == lc.PERMIT_STATUS_ACTIVE


@pytest.mark.asyncio
async def test_update_non_active_conflicts(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="x", issued_at=date.today(), valid_until=None, position_id=None,
        )
        await svc.revoke_permit(session, tenant_id=person.tenant_id, permit_id=permit.id)
        with pytest.raises(lc.PermitTransitionError):
            await svc.update_permit(
                session, tenant_id=person.tenant_id, permit_id=permit.id, permit_type="y",
            )


@pytest.mark.asyncio
async def test_expire_due_flips_overdue_active(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="a", issued_at=date.today() - timedelta(days=5),
            valid_until=date.today() + timedelta(days=5), position_id=None,
        )
        # Force active-but-overdue, then materialise expiry.
        permit.valid_until = date.today() - timedelta(days=1)
        permit.status = lc.PERMIT_STATUS_ACTIVE
        await session.flush()

        count = await svc.expire_due(session, tenant_id=person.tenant_id)
        assert count == 1
        await session.refresh(permit)
        assert permit.status == lc.PERMIT_STATUS_EXPIRED
```

`data_factory.create_person(session=session)` is also valid if you want the person in the same session; here the default (own session, committed) is fine because the new `sessionmaker()` session sees the committed row. `person.tenant_id` / `person.id` are plain scalar columns, safe to read after the factory session closes.

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_permit_service.py -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: FAIL — `AttributeError: module 'app.domains.permits.service' has no attribute 'create_permit'`.

- [ ] **Step 3: Write the service**

```python
# backend/app/domains/permits/service.py
"""Session-aware operations for personal permits (личные допуски)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.permits import lifecycle as lc
from app.models.models import Permit


def _today() -> date:
    return date.today()


async def _get(session: AsyncSession, tenant_id: str, permit_id: str) -> Permit | None:
    stmt = select(Permit).where(Permit.id == permit_id, Permit.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_permit(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_id: str,
    permit_type: str,
    issued_at: date | None = None,
    valid_until: date | None = None,
    position_id: str | None = None,
) -> Permit:
    """Create a permit. Caller must have validated person/position existence."""
    issued = issued_at or _today()
    status = lc.due_status(lc.PERMIT_STATUS_ACTIVE, valid_until, _today())
    permit = Permit(
        tenant_id=tenant_id,
        person_id=person_id,
        position_id=position_id,
        permit_type=permit_type,
        issued_at=issued,
        valid_until=valid_until,
        status=status,
    )
    session.add(permit)
    await session.flush()
    await session.refresh(permit)
    return permit


async def update_permit(
    session: AsyncSession,
    *,
    tenant_id: str,
    permit_id: str,
    permit_type: str | None = None,
    valid_until: date | None = None,
    position_id: str | None = None,
    valid_until_set: bool = False,
    position_id_set: bool = False,
) -> Permit | None:
    """Edit an active permit. None when not found; PermitTransitionError when not active.

    ``*_set`` flags distinguish «field omitted» from «field set to None», so that
    valid_until/position_id can be explicitly cleared.
    """
    permit = await _get(session, tenant_id, permit_id)
    if permit is None:
        return None
    if permit.status != lc.PERMIT_STATUS_ACTIVE:
        raise lc.PermitTransitionError(str(permit.status), "edit")
    if permit_type is not None:
        permit.permit_type = permit_type
    if valid_until_set:
        permit.valid_until = valid_until
    if position_id_set:
        permit.position_id = position_id
    await session.flush()
    await session.refresh(permit)
    return permit


async def extend_permit(
    session: AsyncSession,
    *,
    tenant_id: str,
    permit_id: str,
    valid_until: date,
) -> Permit | None:
    """Extend/re-validate a permit. None when not found; revoked -> PermitTransitionError."""
    permit = await _get(session, tenant_id, permit_id)
    if permit is None:
        return None
    if str(permit.status) == lc.PERMIT_STATUS_REVOKED:
        lc.validate_transition(lc.PERMIT_STATUS_REVOKED, lc.PERMIT_STATUS_ACTIVE)  # raises
    permit.valid_until = valid_until
    permit.status = lc.PERMIT_STATUS_ACTIVE
    await session.flush()
    await session.refresh(permit)
    return permit


async def revoke_permit(
    session: AsyncSession, *, tenant_id: str, permit_id: str
) -> Permit | None:
    """Revoke an active permit. None when not found; PermitTransitionError otherwise."""
    permit = await _get(session, tenant_id, permit_id)
    if permit is None:
        return None
    lc.validate_transition(str(permit.status), lc.PERMIT_STATUS_REVOKED)
    permit.status = lc.PERMIT_STATUS_REVOKED
    await session.flush()
    await session.refresh(permit)
    return permit


async def expire_due(session: AsyncSession, *, tenant_id: str | None = None) -> int:
    """Flip overdue active permits to expired. Returns the number updated."""
    today = _today()
    stmt = select(Permit).where(
        Permit.status == lc.PERMIT_STATUS_ACTIVE,
        Permit.valid_until.is_not(None),
        Permit.valid_until < today,
    )
    if tenant_id is not None:
        stmt = stmt.where(Permit.tenant_id == tenant_id)
    permits = (await session.execute(stmt)).scalars().all()
    for permit in permits:
        permit.status = lc.PERMIT_STATUS_EXPIRED
    if permits:
        await session.flush()
    return len(permits)
```

Append the service re-exports to `backend/app/domains/permits/__init__.py`:

```python
from app.domains.permits.service import (
    create_permit,
    expire_due,
    extend_permit,
    revoke_permit,
    update_permit,
)
```
and add `"create_permit", "expire_due", "extend_permit", "revoke_permit", "update_permit"` to `__all__`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_permit_service.py -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/permits/ tests/test_permit_service.py
git commit -m "feat(permits): service create/update/extend/revoke/expire_due"
```

---

## Task 4: Схемы + CRUD API + регистрация роутера

**Files:**
- Create: `backend/app/schemas/permit.py`
- Create: `backend/app/api/routes/permits.py`
- Modify: `backend/app/api/v1/route_groups.py`
- Test: `tests/api/test_permits_api.py`

- [ ] **Step 1: Write the failing API test**

```python
# tests/api/test_permits_api.py
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status

from app.models.models import RoleEnum

BASE = "/api/v1/permits"


@pytest.mark.asyncio
async def test_permits_crud_extend_revoke(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()

    # create
    r = await async_client.post(BASE, headers=headers, json={
        "person_id": str(person.id),
        "permit_type": "Работа на высоте",
        "valid_until": (date.today() + timedelta(days=30)).isoformat(),
    })
    assert r.status_code == status.HTTP_201_CREATED, r.text
    permit_id = r.json()["id"]
    assert r.json()["status"] == "active"
    assert r.json()["is_expired"] is False

    # list (filter by person)
    r = await async_client.get(BASE, headers=headers, params={"person_id": str(person.id)})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["total"] >= 1

    # extend
    r = await async_client.post(f"{BASE}/{permit_id}/extend", headers=headers, json={
        "valid_until": (date.today() + timedelta(days=90)).isoformat(),
    })
    assert r.status_code == status.HTTP_200_OK

    # revoke
    r = await async_client.post(f"{BASE}/{permit_id}/revoke", headers=headers)
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["status"] == "revoked"

    # editing a revoked permit -> 409
    r = await async_client.patch(f"{BASE}/{permit_id}", headers=headers, json={"permit_type": "z"})
    assert r.status_code == status.HTTP_409_CONFLICT


@pytest.mark.asyncio
async def test_create_permit_unknown_person_404(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await data_factory.ensure_tenant(slug="test")  # ensure the auth tenant exists
    r = await async_client.post(BASE, headers=headers, json={
        "person_id": "does-not-exist", "permit_type": "x",
    })
    assert r.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_expired_only_filter(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()
    await async_client.post(BASE, headers=headers, json={
        "person_id": str(person.id), "permit_type": "old",
        "issued_at": (date.today() - timedelta(days=10)).isoformat(),
        "valid_until": (date.today() - timedelta(days=1)).isoformat(),
    })
    r = await async_client.get(BASE, headers=headers, params={"expired_only": "true"})
    assert r.status_code == status.HTTP_200_OK
    assert all(item["status"] == "expired" for item in r.json()["items"])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/api/test_permits_api.py -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: FAIL — 404 on `/api/v1/permits` (route not registered).

- [ ] **Step 3: Write the schemas**

```python
# backend/app/schemas/permit.py
"""Schemas for personal permits (личные допуски)."""
from __future__ import annotations

from datetime import date, datetime

from app.schemas.base import BaseSchema


class PermitCreate(BaseSchema):
    person_id: str
    permit_type: str
    issued_at: date | None = None
    valid_until: date | None = None
    position_id: str | None = None


class PermitUpdate(BaseSchema):
    permit_type: str | None = None
    valid_until: date | None = None
    position_id: str | None = None


class PermitExtend(BaseSchema):
    valid_until: date


class PermitRead(BaseSchema):
    id: str
    person_id: str
    position_id: str | None
    permit_type: str
    issued_at: date
    valid_until: date | None
    status: str
    is_expired: bool
    created_at: datetime
    updated_at: datetime


class PermitPage(BaseSchema):
    items: list[PermitRead]
    total: int
```

- [ ] **Step 4: Write the routes**

```python
# backend/app/api/routes/permits.py
"""Endpoints for personal permits (личные допуски): CRUD + lifecycle operations."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.permits import (
    create_permit,
    extend_permit,
    revoke_permit,
    update_permit,
)
from app.domains.permits import lifecycle as lc
from app.models.models import Permit, Person, Position
from app.models.tenanting import Tenant
from app.schemas.permit import (
    PermitCreate,
    PermitExtend,
    PermitPage,
    PermitRead,
    PermitUpdate,
)

router = APIRouter(prefix="/permits", tags=["permits"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


# Mirrors ppe.py ABAC (admin-only). Broaden these lists if HR/manager read is needed.
_PERMIT_READ_ROLES = ["admin"]
_PERMIT_WRITE_ROLES = ["admin"]

ReaderAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=_PERMIT_READ_ROLES))
]
WriterAccess = Annotated[
    AccessContext, Depends(abac(_tenant_resource_id, required_roles=_PERMIT_WRITE_ROLES))
]


def _transition_conflict(exc: lc.PermitTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="PERMIT_TRANSITION_INVALID", message=str(exc), error_type="permit"
        ),
    )


def _permit_schema(permit: Permit) -> PermitRead:
    return PermitRead(
        id=str(permit.id),
        person_id=str(permit.person_id),
        position_id=str(permit.position_id) if permit.position_id else None,
        permit_type=permit.permit_type,
        issued_at=permit.issued_at,
        valid_until=permit.valid_until,
        status=str(permit.status),
        is_expired=lc.is_expired(str(permit.status), permit.valid_until, date.today()),
        created_at=permit.created_at,
        updated_at=permit.updated_at,
    )


async def _get_permit_or_404(session: AsyncSession, tenant: Tenant, permit_id: str) -> Permit:
    stmt = select(Permit).where(Permit.id == permit_id, Permit.tenant_id == tenant.id)
    permit = (await session.execute(stmt)).scalar_one_or_none()
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return permit


async def _ensure_person(session: AsyncSession, tenant: Tenant, person_id: str) -> None:
    stmt = select(Person.id).where(
        Person.id == person_id, Person.tenant_id == tenant.id, Person.deleted_at.is_(None)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found")


async def _ensure_position(session: AsyncSession, tenant: Tenant, position_id: str) -> None:
    stmt = select(Position.id).where(
        Position.id == position_id, Position.tenant_id == tenant.id, Position.deleted_at.is_(None)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "position not found")


@router.get("", response_model=PermitPage)
async def list_permits(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    person_id: str | None = None,
    status_filter: str | None = Query(None, alias="status"),
    expired_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PermitPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(Permit).where(Permit.tenant_id == tenant.id)
    count_stmt = select(func.count()).select_from(Permit).where(Permit.tenant_id == tenant.id)
    if person_id:
        stmt = stmt.where(Permit.person_id == person_id)
        count_stmt = count_stmt.where(Permit.person_id == person_id)
    if status_filter:
        stmt = stmt.where(Permit.status == status_filter)
        count_stmt = count_stmt.where(Permit.status == status_filter)
    if expired_only:
        stmt = stmt.where(Permit.status == lc.PERMIT_STATUS_EXPIRED)
        count_stmt = count_stmt.where(Permit.status == lc.PERMIT_STATUS_EXPIRED)
    stmt = stmt.order_by(Permit.issued_at.desc()).limit(limit).offset(offset)
    permits = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    return PermitPage(items=[_permit_schema(p) for p in permits], total=total)


@router.post("", response_model=PermitRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "permit")
async def create_permit_endpoint(
    payload: PermitCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _ensure_person(session, tenant, payload.person_id)
    if payload.position_id:
        await _ensure_position(session, tenant, payload.position_id)
    permit = await create_permit(
        session, tenant_id=tenant.id, person_id=payload.person_id,
        permit_type=payload.permit_type, issued_at=payload.issued_at,
        valid_until=payload.valid_until, position_id=payload.position_id,
    )
    return _permit_schema(permit)


@router.get("/{permit_id}", response_model=PermitRead)
async def get_permit(
    permit_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return _permit_schema(await _get_permit_or_404(session, tenant, permit_id))


@router.patch("/{permit_id}", response_model=PermitRead)
@audit_operation("update", "permit")
async def update_permit_endpoint(
    permit_id: str, payload: PermitUpdate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    fields = payload.model_dump(exclude_unset=True)
    if payload.position_id:
        await _ensure_position(session, tenant, payload.position_id)
    try:
        permit = await update_permit(
            session, tenant_id=tenant.id, permit_id=permit_id,
            permit_type=fields.get("permit_type"),
            valid_until=fields.get("valid_until"),
            position_id=fields.get("position_id"),
            valid_until_set="valid_until" in fields,
            position_id_set="position_id" in fields,
        )
    except lc.PermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return _permit_schema(permit)


@router.post("/{permit_id}/extend", response_model=PermitRead)
@audit_operation("update", "permit")
async def extend_permit_endpoint(
    permit_id: str, payload: PermitExtend, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        permit = await extend_permit(
            session, tenant_id=tenant.id, permit_id=permit_id, valid_until=payload.valid_until
        )
    except lc.PermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return _permit_schema(permit)


@router.post("/{permit_id}/revoke", response_model=PermitRead)
@audit_operation("update", "permit")
async def revoke_permit_endpoint(
    permit_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> PermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        permit = await revoke_permit(session, tenant_id=tenant.id, permit_id=permit_id)
    except lc.PermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    if permit is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "permit not found")
    return _permit_schema(permit)
```

- [ ] **Step 5: Register the router**

In `backend/app/api/v1/route_groups.py`, add `permits` to the import block (right after `persons,`):

```python
    persons,
    permits,
    ppe,
```

and add the registration tuple right after the ppe entry (around line 110):

```python
    (ppe.router, {"tags": ["ppe"]}),
    (permits.router, {"tags": ["permits"]}),
```

- [ ] **Step 6: Run the API test**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/api/test_permits_api.py -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/permit.py backend/app/api/routes/permits.py backend/app/api/v1/route_groups.py tests/api/test_permits_api.py
git commit -m "feat(permits): CRUD + extend/revoke API + router wiring"
```

---

## Task 5: Beat `permits.expiry.tick`

**Files:**
- Modify: `backend/app/tasks/_core.py` (add task, mirror `ppe_expiry_tick`)
- Modify: `backend/app/services/celery_app.py` (beat schedule)
- Test: `tests/test_permits_expire_tick.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_permits_expire_tick.py
from datetime import date, timedelta

import pytest

from app.domains.permits import lifecycle as lc
from app.domains.permits import service as svc


@pytest.mark.asyncio
async def test_expire_due_idempotent(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        permit = await svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="a", issued_at=date.today() - timedelta(days=5),
            valid_until=date.today() + timedelta(days=5), position_id=None,
        )
        permit.valid_until = date.today() - timedelta(days=1)
        permit.status = lc.PERMIT_STATUS_ACTIVE
        await session.flush()

        first = await svc.expire_due(session, tenant_id=person.tenant_id)
        second = await svc.expire_due(session, tenant_id=person.tenant_id)
        assert first == 1
        assert second == 0  # already expired — idempotent
```

- [ ] **Step 2: Run the test to verify it passes (contract guard)**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_permits_expire_tick.py -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: PASS — this exercises `expire_due` (Task 3) and guards the idempotency contract the beat relies on. Proceed to wire the beat in Step 3.

- [ ] **Step 3: Add the Celery task**

In `backend/app/tasks/_core.py`, after the `_ppe_expiry_tick` block (around line 1955), add:

```python
@celery_app.task(
    name="permits.expiry.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def permits_expiry_tick() -> int:
    return _run_coroutine(_permits_expiry_tick())


async def _permits_expiry_tick() -> int:
    from app.domains.permits.service import expire_due

    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all()
        )
    total = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                # Idempotent: re-running on the same day flips nothing new.
                total += await expire_due(session, tenant_id=tenant_id)
                await session.commit()
    return total
```

- [ ] **Step 4: Add the beat schedule entry**

In `backend/app/services/celery_app.py`, add to `beat_schedule` (right after the `ppe-expiry-daily` entry, around line 84):

```python
    "permits-expiry-daily": {
        "task": "permits.expiry.tick",
        "schedule": crontab(hour=4, minute=30),
    },
```

- [ ] **Step 5: Run the test + a beat-wiring smoke**

Run:
```
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_permits_expire_tick.py -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -c "from app.tasks._core import permits_expiry_tick; from app.services.celery_app import celery_app; assert 'permits-expiry-daily' in celery_app.conf.beat_schedule; print('beat ok')"
```
Expected: test PASS; smoke prints `beat ok`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/tasks/_core.py backend/app/services/celery_app.py tests/test_permits_expire_tick.py
git commit -m "feat(permits): permits.expiry.tick daily beat (auto-expire)"
```

---

## Task 6: Контурная регрессия + handoff

- [ ] **Step 1: Run the full permits cohort + adjacent readers**

Run:
```
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_permit_lifecycle.py backend/tests/test_prm01_permit_status_migration.py tests/test_permit_service.py tests/api/test_permits_api.py tests/test_permits_expire_tick.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_employee_card.py tests/test_data_quality.py -p no:xdist --timeout=600 >> _t.txt 2>&1; "EXIT=$LASTEXITCODE"
```
Expected: all PASS. Record the `N passed` summary and any Py3.12-vs-3.13 mismatch (do not abort on version mismatch — CI is canonical).

- [ ] **Step 2: Clean up temp files**

```bash
rm -f _t.txt
```

- [ ] **Step 3: Update the handoff report**

Append a Срез-1 completion note to `AI_IMPLEMENTATION_REPORT.md` (mirror the format of prior slice entries): module touched, migration `prm01`, new endpoints (`/permits` CRUD + extend/revoke), beat `permits.expiry.tick`, tests, and that формальный наряд-допуск §16 is the deferred Срез-2.

- [ ] **Step 4: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(report): handoff — личные допуски Срез-1 complete (prm01 + /permits + beat)"
```
