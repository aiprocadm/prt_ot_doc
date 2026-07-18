# Наряд-допуск §16: ядро + гейт + mobile open/close + фото — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Построить формальный документ «наряд-допуск на работы повышенной опасности»: WorkPermit + бригада + события/история, FSM `draft→issued→suspended→closed/cancelled`, гейт блокировки выдачи по просроченным личным допускам/обучению/медосмотрам, mobile open/close с фотофиксацией.

**Architecture:** Новый домен `domains/work_permits` (чистый FSM + session-aware сервис), модели в `models/work_permit.py` (3 таблицы), гейт в `services/work_permit_admission.py` (переиспользует `domains/permits` Среза-1), схемы + роуты `/work-permits`. Зеркалит паттерны `domains/ppe` / `domains/permits` / `IncidentPerson` / `contractor_admission`.

**Tech Stack:** Python 3.12 (CI; локально Py3.13/.venv), FastAPI, SQLAlchemy 2.0 async, Alembic, pytest.

**Ветка:** `feat/work-permits` (стопкой поверх `feat/permits-lifecycle`; спек уже закоммичена). Спека: `docs/superpowers/specs/2026-06-16-work-permits-design.md`.

**Локальный прогон (Win/Py3.13/.venv):** PowerShell→file, итог по EXIT (см. [[py313_win_pytest_invocation]]):
`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest <путь> -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"` → читать `_t.txt`. App-fixture тесты медленные. Канон Py3.12 = CI; расхождение версии указывать, не абортить. После прогонов субагентов проверять `git status`/`git stash list` ([[subagent_stash_hazard]]).

---

## File Structure

**Создать:**
- `backend/app/domains/work_permits/__init__.py` — реэкспорт.
- `backend/app/domains/work_permits/lifecycle.py` — чистый FSM + константы.
- `backend/app/domains/work_permits/service.py` — session-aware операции.
- `backend/app/models/work_permit.py` — `WorkPermit`, `WorkPermitMember`, `WorkPermitEvent`.
- `backend/app/services/work_permit_admission.py` — гейт готовности бригады.
- `backend/app/schemas/work_permit.py` — схемы.
- `backend/app/api/routes/work_permits.py` — роуты.
- `backend/app/migrations/versions/20260616_wp01_work_permit_tables.py` — миграция.
- Тесты: `backend/tests/test_work_permit_lifecycle.py`, `backend/tests/test_wp01_work_permit_migration.py`, `tests/test_work_permit_service.py`, `tests/test_work_permit_admission.py`, `tests/api/test_work_permits_api.py`.

**Изменить:**
- `backend/app/models/__init__.py` — импорт новых моделей (рядом с `from app.models.file import File`).
- `backend/app/api/v1/route_groups.py` — регистрация роутера.

---

## Task 1: Чистый lifecycle-модуль (FSM + константы)

**Files:**
- Create: `backend/app/domains/work_permits/lifecycle.py`
- Create: `backend/app/domains/work_permits/__init__.py`
- Test: `backend/tests/test_work_permit_lifecycle.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_work_permit_lifecycle.py
import pytest

from app.domains.work_permits import lifecycle as lc


def test_status_constants():
    assert lc.STATUS_DRAFT == "draft"
    assert lc.STATUS_ISSUED == "issued"
    assert lc.WORK_PERMIT_STATUSES == frozenset(
        {"draft", "issued", "suspended", "closed", "cancelled"}
    )


def test_allowed_transitions():
    lc.validate_transition(lc.STATUS_DRAFT, lc.STATUS_ISSUED)
    lc.validate_transition(lc.STATUS_ISSUED, lc.STATUS_SUSPENDED)
    lc.validate_transition(lc.STATUS_SUSPENDED, lc.STATUS_ISSUED)
    lc.validate_transition(lc.STATUS_ISSUED, lc.STATUS_CLOSED)


def test_forbidden_transitions_raise():
    with pytest.raises(lc.WorkPermitTransitionError):
        lc.validate_transition(lc.STATUS_CLOSED, lc.STATUS_ISSUED)      # terminal
    with pytest.raises(lc.WorkPermitTransitionError):
        lc.validate_transition(lc.STATUS_DRAFT, lc.STATUS_SUSPENDED)    # not allowed
    with pytest.raises(lc.WorkPermitTransitionError):
        lc.validate_transition("bogus", lc.STATUS_ISSUED)              # unknown


def test_value_validators():
    assert lc.is_work_type("hot_work") is True
    assert lc.is_work_type("nope") is False
    assert lc.is_member_role("foreman") is True
    assert lc.is_member_role("nope") is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_lifecycle.py -p no:xdist --timeout=120 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domains.work_permits'`.

- [ ] **Step 3: Write the lifecycle module**

```python
# backend/app/domains/work_permits/lifecycle.py
"""Pure work-permit (наряд-допуск) lifecycle rules: FSM + value vocabularies.

No I/O / no sqlalchemy imports — mirrors ``domains/permits/lifecycle.py``.
All values are the canonical VARCHAR strings stored in the DB (see migration wp01).
"""
from __future__ import annotations

STATUS_DRAFT = "draft"
STATUS_ISSUED = "issued"
STATUS_SUSPENDED = "suspended"
STATUS_CLOSED = "closed"
STATUS_CANCELLED = "cancelled"

WORK_PERMIT_STATUSES = frozenset({
    STATUS_DRAFT, STATUS_ISSUED, STATUS_SUSPENDED, STATUS_CLOSED, STATUS_CANCELLED,
})

# огневые / газоопасные / на высоте / замкнутое пространство / земляные / электро
WORK_TYPES = frozenset({
    "hot_work", "gas_hazardous", "height", "confined_space", "excavation", "electrical",
})

# выдающий наряд / ответственный руководитель / допускающий / производитель работ /
# наблюдающий / член бригады
MEMBER_ROLES = frozenset({
    "issuer", "supervisor", "admitter", "foreman", "observer", "member",
})

EVENT_TYPES = frozenset({
    "issued", "suspended", "resumed", "closed", "cancelled", "extended",
})

ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    STATUS_DRAFT: frozenset({STATUS_ISSUED, STATUS_CANCELLED}),
    STATUS_ISSUED: frozenset({STATUS_SUSPENDED, STATUS_CLOSED, STATUS_CANCELLED}),
    STATUS_SUSPENDED: frozenset({STATUS_ISSUED, STATUS_CLOSED, STATUS_CANCELLED}),
    STATUS_CLOSED: frozenset(),
    STATUS_CANCELLED: frozenset(),
}


class WorkPermitTransitionError(ValueError):
    """Invalid work-permit status transition (maps to HTTP 409)."""

    def __init__(self, current: str, target: str) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid work-permit transition: {current!r} -> {target!r}")


def validate_transition(current: str, target: str) -> None:
    """Raise WorkPermitTransitionError unless current -> target is allowed."""
    if current not in WORK_PERMIT_STATUSES or target not in WORK_PERMIT_STATUSES:
        raise WorkPermitTransitionError(current, target)
    if target not in ALLOWED_TRANSITIONS[current]:
        raise WorkPermitTransitionError(current, target)


def is_work_type(value: str) -> bool:
    return value in WORK_TYPES


def is_member_role(value: str) -> bool:
    return value in MEMBER_ROLES
```

```python
# backend/app/domains/work_permits/__init__.py
"""Domain logic for work permits (наряды-допуски)."""

from app.domains.work_permits.lifecycle import (
    ALLOWED_TRANSITIONS,
    EVENT_TYPES,
    MEMBER_ROLES,
    STATUS_CANCELLED,
    STATUS_CLOSED,
    STATUS_DRAFT,
    STATUS_ISSUED,
    STATUS_SUSPENDED,
    WORK_PERMIT_STATUSES,
    WORK_TYPES,
    WorkPermitTransitionError,
    is_member_role,
    is_work_type,
    validate_transition,
)

__all__ = [
    "ALLOWED_TRANSITIONS", "EVENT_TYPES", "MEMBER_ROLES",
    "STATUS_CANCELLED", "STATUS_CLOSED", "STATUS_DRAFT", "STATUS_ISSUED", "STATUS_SUSPENDED",
    "WORK_PERMIT_STATUSES", "WORK_TYPES", "WorkPermitTransitionError",
    "is_member_role", "is_work_type", "validate_transition",
]
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_lifecycle.py -p no:xdist --timeout=120 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/ backend/tests/test_work_permit_lifecycle.py
git commit -m "feat(work-permits): pure FSM lifecycle + value vocabularies (Срез-2)"
```

---

## Task 2: Модели + миграция wp01 + регистрация + guard-тест

**Files:**
- Create: `backend/app/models/work_permit.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/app/migrations/versions/20260616_wp01_work_permit_tables.py`
- Test: `backend/tests/test_wp01_work_permit_migration.py`

- [ ] **Step 1: Write the failing guard test**

```python
# backend/tests/test_wp01_work_permit_migration.py
"""wp01 migration + model shape (mirrors test_sz01/test_prm01 — read file as text)."""
from __future__ import annotations

from pathlib import Path

from app.models.work_permit import WorkPermit, WorkPermitEvent, WorkPermitMember

MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260616_wp01_work_permit_tables.py"
)


def test_models_tables_and_status_varchar():
    assert WorkPermit.__tablename__ == "work_permit"
    assert WorkPermitMember.__tablename__ == "work_permit_member"
    assert WorkPermitEvent.__tablename__ == "work_permit_event"
    status = WorkPermit.__table__.c["status"]
    assert type(status.type).__name__ == "String"
    assert status.type.length == 32


def test_migration_revision_chain():
    src = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260616_wp01_work_permit_tables"' in src
    assert 'down_revision = "20260615_prm01_permit_status_varchar"' in src


def test_migration_creates_three_tables_with_literal_names():
    src = MIGRATION.read_text(encoding="utf-8")
    for table in ("work_permit", "work_permit_member", "work_permit_event"):
        assert f'"{table}"' in src, table
    # downgrade drops in reverse dependency order (children before parent)
    assert src.index('drop_table("work_permit_event")') < src.index('drop_table("work_permit")')
    assert src.index('drop_table("work_permit_member")') < src.index('drop_table("work_permit")')
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_wp01_work_permit_migration.py -p no:xdist --timeout=120 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.work_permit'`.

- [ ] **Step 3: Write the models**

```python
# backend/app/models/work_permit.py
"""Work-permit (наряд-допуск) models: document + brigade members + event log."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantBaseModel


class WorkPermit(TenantBaseModel):
    __tablename__ = "work_permit"

    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    work_type: Mapped[str] = mapped_column(String(32), nullable=False)
    zone_text: Mapped[str] = mapped_column(String(255), nullable=False)
    site_id: Mapped[str | None] = mapped_column(
        ForeignKey("site.id", ondelete="SET NULL"), nullable=True, index=True
    )
    equipment_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    hazards_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    measures_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_work_permit_tenant_number"),
        Index("ix_work_permit_status", "tenant_id", "status"),
    )


class WorkPermitMember(TenantBaseModel):
    __tablename__ = "work_permit_member"

    work_permit_id: Mapped[str] = mapped_column(
        ForeignKey("work_permit.id", ondelete="CASCADE"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(
        ForeignKey("person.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "work_permit_id", "person_id", "role",
            name="uq_work_permit_member",
        ),
    )


class WorkPermitEvent(TenantBaseModel):
    __tablename__ = "work_permit_event"

    work_permit_id: Mapped[str] = mapped_column(
        ForeignKey("work_permit.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    photo_file_id: Mapped[str | None] = mapped_column(
        ForeignKey("file.id", ondelete="SET NULL"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

Then register the models in `backend/app/models/__init__.py` — add next to `from app.models.file import File` (around line 16):
```python
from app.models.work_permit import WorkPermit, WorkPermitEvent, WorkPermitMember
```
If `__init__.py` has an `__all__`, append `"WorkPermit"`, `"WorkPermitMember"`, `"WorkPermitEvent"`.

- [ ] **Step 4: Write the migration**

First confirm the head: from repo root `& .\.venv\Scripts\python.exe -m alembic -c backend/app/migrations/alembic.ini heads` must print `20260615_prm01_permit_status_varchar (head)`. If different, STOP and report NEEDS_CONTEXT with the actual head.

```python
# backend/app/migrations/versions/20260616_wp01_work_permit_tables.py
"""wp01: work-permit (наряд-допуск) tables — document + members + events.

Additive: three new tables. VARCHAR vocabularies (status/work_type/role/event_type),
no native enums (анти-грабли enum-parity). FKs to existing site/person/file/work_permit.
Names are LITERAL (AST-audit blindspot). Round-trip-safe: downgrade drops children
before the parent.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260616_wp01_work_permit_tables"
down_revision = "20260615_prm01_permit_status_varchar"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    op.create_table(
        "work_permit",
        *_base_columns(),
        sa.Column("number", sa.String(length=64), nullable=True),
        sa.Column("work_type", sa.String(length=32), nullable=False),
        sa.Column("zone_text", sa.String(length=255), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("equipment_text", sa.Text(), nullable=True),
        sa.Column("hazards_text", sa.Text(), nullable=True),
        sa.Column("measures_text", sa.Text(), nullable=True),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "number", name="uq_work_permit_tenant_number"),
    )
    op.create_index("ix_work_permit_status", "work_permit", ["tenant_id", "status"])
    op.create_index("ix_work_permit_site", "work_permit", ["tenant_id", "site_id"])

    op.create_table(
        "work_permit_member",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id", "work_permit_id", "person_id", "role", name="uq_work_permit_member"
        ),
    )
    op.create_index("ix_work_permit_member_permit", "work_permit_member", ["work_permit_id"])
    op.create_index("ix_work_permit_member_person", "work_permit_member", ["person_id"])

    op.create_table(
        "work_permit_event",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("photo_file_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_file_id"], ["file.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_work_permit_event_permit", "work_permit_event", ["work_permit_id"])


def downgrade() -> None:
    op.drop_table("work_permit_event")
    op.drop_table("work_permit_member")
    op.drop_table("work_permit")
```

- [ ] **Step 5: Run the guard test, confirm PASS**

Run: `$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_wp01_work_permit_migration.py -p no:xdist --timeout=120 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: PASS (3 passed). (Note: the model-shape test imports the models; the migration text-asserts confirm chain + literal names + drop order.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/work_permit.py backend/app/models/__init__.py backend/app/migrations/versions/20260616_wp01_work_permit_tables.py backend/tests/test_wp01_work_permit_migration.py
git commit -m "feat(work-permits): models + wp01 migration (3 tables) + registration"
```

---

## Task 3: Сервис документа (CRUD + члены + события + переходы)

**Files:**
- Create: `backend/app/domains/work_permits/service.py`
- Modify: `backend/app/domains/work_permits/__init__.py` (реэкспорт сервиса)
- Test: `tests/test_work_permit_service.py`

> The gate (`issue`) is wired in Task 4; here `issue` performs ONLY the FSM transition + event (no readiness check yet). Task 4 inserts the gate call.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_work_permit_service.py
from datetime import datetime, timezone

import pytest

from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc


def _now():
    return datetime(2026, 6, 16, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_create_add_member_issue_suspend_resume_close(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="hot_work",
            zone_text="Цех 1", number="НД-1",
        )
        assert wp.status == lc.STATUS_DRAFT

        member = await svc.add_member(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            person_id=person.id, role="foreman",
        )
        assert member.role == "foreman"

        issued = await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert issued.status == lc.STATUS_ISSUED
        assert issued.opened_at is not None

        sus = await svc.suspend(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert sus.status == lc.STATUS_SUSPENDED
        res = await svc.resume(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert res.status == lc.STATUS_ISSUED
        closed = await svc.close(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert closed.status == lc.STATUS_CLOSED

        events = await svc.list_events(session, tenant_id=person.tenant_id, work_permit_id=wp.id)
        assert [e.event_type for e in events] == ["issued", "suspended", "resumed", "closed"]


@pytest.mark.asyncio
async def test_update_only_in_draft(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="Кровля",
        )
        await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        with pytest.raises(lc.WorkPermitTransitionError):
            await svc.update_work_permit(
                session, tenant_id=person.tenant_id, work_permit_id=wp.id, zone_text="x",
            )


@pytest.mark.asyncio
async def test_cancel_and_extend(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="electrical", zone_text="ТП-3",
        )
        await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        extended = await svc.extend(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            planned_end=_now(), actor_user_id="u1",
        )
        assert extended.planned_end == _now()
        cancelled = await svc.cancel(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert cancelled.status == lc.STATUS_CANCELLED
```

- [ ] **Step 2: Run, confirm it fails** (`module 'app.domains.work_permits.service' has no attribute 'create_work_permit'`):

`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_work_permit_service.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`

- [ ] **Step 3: Write the service**

```python
# backend/app/domains/work_permits/service.py
"""Session-aware operations for work permits (наряды-допуски)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.work_permits import lifecycle as lc
from app.models.work_permit import WorkPermit, WorkPermitEvent, WorkPermitMember


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _get(session: AsyncSession, tenant_id: str, work_permit_id: str) -> WorkPermit | None:
    stmt = select(WorkPermit).where(
        WorkPermit.id == work_permit_id, WorkPermit.tenant_id == tenant_id
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def _log(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, event_type: str,
    actor_user_id: str | None, photo_file_id: str | None = None, note: str | None = None,
) -> WorkPermitEvent:
    event = WorkPermitEvent(
        tenant_id=tenant_id, work_permit_id=work_permit_id, event_type=event_type,
        at=_now(), actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )
    session.add(event)
    await session.flush()
    return event


async def create_work_permit(
    session: AsyncSession, *, tenant_id: str, work_type: str, zone_text: str,
    number: str | None = None, site_id: str | None = None, equipment_text: str | None = None,
    hazards_text: str | None = None, measures_text: str | None = None,
    planned_start: datetime | None = None, planned_end: datetime | None = None,
) -> WorkPermit:
    wp = WorkPermit(
        tenant_id=tenant_id, work_type=work_type, zone_text=zone_text, number=number,
        site_id=site_id, equipment_text=equipment_text, hazards_text=hazards_text,
        measures_text=measures_text, planned_start=planned_start, planned_end=planned_end,
        status=lc.STATUS_DRAFT,
    )
    session.add(wp)
    await session.flush()
    await session.refresh(wp)
    return wp


_DRAFT_EDITABLE = ("number", "work_type", "zone_text", "site_id", "equipment_text",
                   "hazards_text", "measures_text", "planned_start", "planned_end")


async def update_work_permit(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, **fields,
) -> WorkPermit | None:
    """Edit a draft permit. None if not found; WorkPermitTransitionError if not draft.

    Only keys in ``fields`` that are present are applied (caller passes exactly the
    fields to change; pass None explicitly to clear a nullable column)."""
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status != lc.STATUS_DRAFT:
        raise lc.WorkPermitTransitionError(str(wp.status), "edit")
    for key, value in fields.items():
        if key in _DRAFT_EDITABLE:
            setattr(wp, key, value)
    await session.flush()
    await session.refresh(wp)
    return wp


async def delete_draft(session: AsyncSession, *, tenant_id: str, work_permit_id: str) -> bool:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return False
    if wp.status != lc.STATUS_DRAFT:
        raise lc.WorkPermitTransitionError(str(wp.status), "delete")
    await session.delete(wp)
    await session.flush()
    return True


_TERMINAL = (lc.STATUS_CLOSED, lc.STATUS_CANCELLED)


async def add_member(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, person_id: str, role: str,
) -> WorkPermitMember | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status in _TERMINAL:
        raise lc.WorkPermitTransitionError(str(wp.status), "add_member")
    member = WorkPermitMember(
        tenant_id=tenant_id, work_permit_id=work_permit_id, person_id=person_id, role=role,
    )
    session.add(member)
    await session.flush()
    await session.refresh(member)
    return member


async def remove_member(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, member_id: str,
) -> bool:
    stmt = select(WorkPermitMember).where(
        WorkPermitMember.id == member_id,
        WorkPermitMember.work_permit_id == work_permit_id,
        WorkPermitMember.tenant_id == tenant_id,
    )
    member = (await session.execute(stmt)).scalar_one_or_none()
    if member is None:
        return False
    await session.delete(member)
    await session.flush()
    return True


async def list_members(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> list[WorkPermitMember]:
    stmt = select(WorkPermitMember).where(
        WorkPermitMember.tenant_id == tenant_id,
        WorkPermitMember.work_permit_id == work_permit_id,
    ).order_by(WorkPermitMember.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def list_events(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str,
) -> list[WorkPermitEvent]:
    stmt = select(WorkPermitEvent).where(
        WorkPermitEvent.tenant_id == tenant_id,
        WorkPermitEvent.work_permit_id == work_permit_id,
    ).order_by(WorkPermitEvent.at.asc(), WorkPermitEvent.created_at.asc())
    return list((await session.execute(stmt)).scalars().all())


async def _transition(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str, target: str,
    event_type: str, actor_user_id: str | None, photo_file_id: str | None = None,
    note: str | None = None,
) -> WorkPermit | None:
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    lc.validate_transition(str(wp.status), target)
    wp.status = target
    if target == lc.STATUS_ISSUED and wp.opened_at is None:
        wp.opened_at = _now()
    if target == lc.STATUS_SUSPENDED:
        wp.suspended_at = _now()
    if target == lc.STATUS_CLOSED:
        wp.closed_at = _now()
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type=event_type, actor_user_id=actor_user_id,
        photo_file_id=photo_file_id, note=note,
    )
    await session.flush()
    await session.refresh(wp)
    return wp


async def issue(session, *, tenant_id, work_permit_id, actor_user_id, photo_file_id=None, note=None):
    # Task 4 inserts the brigade-readiness gate immediately before this transition.
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_ISSUED,
        event_type="issued", actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )


async def suspend(session, *, tenant_id, work_permit_id, actor_user_id, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_SUSPENDED,
        event_type="suspended", actor_user_id=actor_user_id, note=note,
    )


async def resume(session, *, tenant_id, work_permit_id, actor_user_id, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_ISSUED,
        event_type="resumed", actor_user_id=actor_user_id, note=note,
    )


async def close(session, *, tenant_id, work_permit_id, actor_user_id, photo_file_id=None, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_CLOSED,
        event_type="closed", actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )


async def cancel(session, *, tenant_id, work_permit_id, actor_user_id, note=None):
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_CANCELLED,
        event_type="cancelled", actor_user_id=actor_user_id, note=note,
    )


async def extend(session, *, tenant_id, work_permit_id, planned_end, actor_user_id, note=None):
    wp = await _get(session, tenant_id, work_permit_id)
    if wp is None:
        return None
    if wp.status not in (lc.STATUS_ISSUED, lc.STATUS_SUSPENDED):
        raise lc.WorkPermitTransitionError(str(wp.status), "extend")
    wp.planned_end = planned_end
    await _log(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id,
        event_type="extended", actor_user_id=actor_user_id, note=note,
    )
    await session.flush()
    await session.refresh(wp)
    return wp
```

Add the service re-exports to `backend/app/domains/work_permits/__init__.py`:
```python
from app.domains.work_permits.service import (
    add_member, cancel, close, create_work_permit, delete_draft, extend, issue,
    list_events, list_members, remove_member, resume, suspend, update_work_permit,
)
```
and append all of them to `__all__`.

- [ ] **Step 4: Run the test, confirm PASS** (3 passed):

`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_work_permit_service.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/work_permits/ tests/test_work_permit_service.py
git commit -m "feat(work-permits): service — document CRUD + members + events + FSM transitions"
```

---

## Task 4: Гейт допуска (work_permit_admission)

**Files:**
- Create: `backend/app/services/work_permit_admission.py`
- Modify: `backend/app/domains/work_permits/service.py` (`issue` calls the gate)
- Test: `tests/test_work_permit_admission.py`

> Reuses `domains/permits/lifecycle.is_expired` for personal permits. Models for the
> readiness checks: `Permit` (status/valid_until, no soft-delete), `MedicalExam`
> (person_id/valid_until/exam_date, SoftDeleteMixin), `TrainingCertificate`
> (person_id/valid_until, SoftDeleteMixin).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_work_permit_admission.py
from datetime import date, timedelta

import pytest

from app.domains.permits import service as permit_svc
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import service as svc
from app.services import work_permit_admission as gate


@pytest.mark.asyncio
async def test_expired_personal_permit_blocks_issue(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        # personal permit that is already expired
        await permit_svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="height", issued_at=date.today() - timedelta(days=10),
            valid_until=date.today() - timedelta(days=1),
        )
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="Кровля",
        )
        await svc.add_member(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            person_id=person.id, role="foreman",
        )
        report = await gate.check_brigade_readiness(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
        )
        assert report.ok is False
        assert any(v.code == "permit_expired" and v.severity == "block" for v in report.violations)

        with pytest.raises(gate.WorkPermitBlocked):
            await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")


@pytest.mark.asyncio
async def test_active_personal_permit_allows_issue(sessionmaker, data_factory):
    person = await data_factory.create_person()
    async with sessionmaker() as session:
        await permit_svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id,
            permit_type="height", issued_at=date.today(),
            valid_until=date.today() + timedelta(days=30),
        )
        wp = await svc.create_work_permit(
            session, tenant_id=person.tenant_id, work_type="height", zone_text="Кровля",
        )
        await svc.add_member(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
            person_id=person.id, role="foreman",
        )
        issued = await svc.issue(session, tenant_id=person.tenant_id, work_permit_id=wp.id, actor_user_id="u1")
        assert issued.status == lc.STATUS_ISSUED
        # medical/training absent → warnings, not blocks
        report = await gate.check_brigade_readiness(
            session, tenant_id=person.tenant_id, work_permit_id=wp.id,
        )
        assert all(v.severity == "warn" for v in report.violations)
```

- [ ] **Step 2: Run, confirm it fails** (`No module named 'app.services.work_permit_admission'`):

`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_work_permit_admission.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`

- [ ] **Step 3: Write the gate**

```python
# backend/app/services/work_permit_admission.py
"""Brigade-readiness gate for issuing a work permit (наряд-допуск).

Blocks issuance when a brigade member has an expired/absent personal permit,
or an expired medical exam / training certificate. Absent medical/training is a
warning (not a block). Reuses the Срез-1 personal-permit lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.permits import lifecycle as plc
from app.models.models import MedicalExam, Permit, TrainingCertificate
from app.models.work_permit import WorkPermitMember


@dataclass(slots=True)
class MemberViolation:
    person_id: str
    role: str
    code: str
    severity: str  # "block" | "warn"


@dataclass(slots=True)
class ReadinessReport:
    ok: bool
    violations: list[MemberViolation]


class WorkPermitBlocked(Exception):
    """Raised on issue when at least one brigade member is blocked (→ HTTP 409)."""

    def __init__(self, violations: list[MemberViolation]) -> None:
        self.violations = violations
        super().__init__("work permit blocked: brigade readiness failed")


def _today() -> date:
    return date.today()


async def _member_violations(
    session: AsyncSession, tenant_id: str, person_id: str, role: str
) -> list[MemberViolation]:
    today = _today()
    out: list[MemberViolation] = []

    permits = (await session.execute(
        select(Permit).where(Permit.tenant_id == tenant_id, Permit.person_id == person_id)
    )).scalars().all()
    has_active_valid = any(
        p.status == plc.PERMIT_STATUS_ACTIVE
        and not plc.is_expired(str(p.status), p.valid_until, today)
        for p in permits
    )
    if not has_active_valid:
        out.append(MemberViolation(
            person_id, role,
            "permit_expired" if permits else "permit_missing", "block",
        ))

    exams = (await session.execute(
        select(MedicalExam).where(
            MedicalExam.tenant_id == tenant_id, MedicalExam.person_id == person_id,
            MedicalExam.deleted_at.is_(None),
        ).order_by(MedicalExam.exam_date.desc())
    )).scalars().all()
    if not exams:
        out.append(MemberViolation(person_id, role, "medical_absent", "warn"))
    elif exams[0].valid_until < today:
        out.append(MemberViolation(person_id, role, "medical_expired", "block"))

    certs = (await session.execute(
        select(TrainingCertificate).where(
            TrainingCertificate.tenant_id == tenant_id,
            TrainingCertificate.person_id == person_id,
            TrainingCertificate.deleted_at.is_(None),
        )
    )).scalars().all()
    if not certs:
        out.append(MemberViolation(person_id, role, "training_absent", "warn"))
    elif not any(c.valid_until is None or c.valid_until >= today for c in certs):
        out.append(MemberViolation(person_id, role, "training_expired", "block"))

    return out


async def check_brigade_readiness(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str
) -> ReadinessReport:
    members = (await session.execute(
        select(WorkPermitMember).where(
            WorkPermitMember.tenant_id == tenant_id,
            WorkPermitMember.work_permit_id == work_permit_id,
        )
    )).scalars().all()
    violations: list[MemberViolation] = []
    for m in members:
        violations.extend(await _member_violations(session, tenant_id, m.person_id, m.role))
    ok = not any(v.severity == "block" for v in violations)
    return ReadinessReport(ok=ok, violations=violations)


async def enforce_brigade_readiness(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str
) -> None:
    report = await check_brigade_readiness(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id
    )
    if not report.ok:
        raise WorkPermitBlocked([v for v in report.violations if v.severity == "block"])
```

- [ ] **Step 4: Wire the gate into `issue`** — in `backend/app/domains/work_permits/service.py`, change the `issue` function to enforce readiness before transitioning:

```python
async def issue(session, *, tenant_id, work_permit_id, actor_user_id, photo_file_id=None, note=None):
    from app.services.work_permit_admission import enforce_brigade_readiness

    if await _get(session, tenant_id, work_permit_id) is None:
        return None
    await enforce_brigade_readiness(session, tenant_id=tenant_id, work_permit_id=work_permit_id)
    return await _transition(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id, target=lc.STATUS_ISSUED,
        event_type="issued", actor_user_id=actor_user_id, photo_file_id=photo_file_id, note=note,
    )
```
(The lazy import avoids a domain→services import cycle.)

- [ ] **Step 5: Run the gate test + service regression, confirm PASS:**

```
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/test_work_permit_admission.py tests/test_work_permit_service.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"
```
Expected: all PASS. (The service test `test_create_add_member_issue_...` issues a permit whose single member has no personal permit → would now be BLOCKED. Fix that test by giving its member an active personal `Permit` before `issue`, mirroring `test_active_personal_permit_allows_issue`. Update the three service tests that call `issue` to seed an active personal permit for the member first.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/work_permit_admission.py backend/app/domains/work_permits/service.py tests/test_work_permit_admission.py tests/test_work_permit_service.py
git commit -m "feat(work-permits): brigade-readiness gate blocks issue on expired permit/medical/training"
```

---

## Task 5: Схемы + CRUD/члены API + регистрация роутера

**Files:**
- Create: `backend/app/schemas/work_permit.py`
- Create: `backend/app/api/routes/work_permits.py` (CRUD + members; actions added in Task 6)
- Modify: `backend/app/api/v1/route_groups.py`
- Test: `tests/api/test_work_permits_api.py` (CRUD + members part)

- [ ] **Step 1: Write the failing API test**

```python
# tests/api/test_work_permits_api.py
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status

from app.models.models import RoleEnum

BASE = "/api/v1/work-permits"


@pytest.mark.asyncio
async def test_work_permit_crud_and_members(async_client, make_auth_headers, data_factory, sessionmaker):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()

    r = await async_client.post(BASE, headers=headers, json={
        "work_type": "hot_work", "zone_text": "Цех 1", "number": "НД-100",
    })
    assert r.status_code == status.HTTP_201_CREATED, r.text
    wp_id = r.json()["id"]
    assert r.json()["status"] == "draft"

    r = await async_client.get(BASE, headers=headers, params={"status": "draft"})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["total"] >= 1

    r = await async_client.patch(f"{BASE}/{wp_id}", headers=headers, json={"zone_text": "Цех 2"})
    assert r.status_code == status.HTTP_200_OK
    assert r.json()["zone_text"] == "Цех 2"

    r = await async_client.post(f"{BASE}/{wp_id}/members", headers=headers, json={
        "person_id": str(person.id), "role": "foreman",
    })
    assert r.status_code == status.HTTP_201_CREATED, r.text
    member_id = r.json()["id"]

    r = await async_client.get(f"{BASE}/{wp_id}", headers=headers)
    assert any(m["id"] == member_id for m in r.json()["members"])

    r = await async_client.delete(f"{BASE}/{wp_id}/members/{member_id}", headers=headers)
    assert r.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.asyncio
async def test_create_member_unknown_person_404(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    r = await async_client.post(f"{BASE}/{wp_id}/members", headers=headers, json={
        "person_id": "missing", "role": "member",
    })
    assert r.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_invalid_work_type_422(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(BASE, headers=headers, json={"work_type": "nope", "zone_text": "z"})
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_work_permits_tenant_isolated(async_client, make_auth_headers, data_factory, sessionmaker):
    headers = await make_auth_headers(RoleEnum.ADMIN)  # tenant "test"
    from app.models.work_permit import WorkPermit
    async with sessionmaker() as session:
        other = await data_factory.ensure_tenant(slug="other", session=session)
        wp = WorkPermit(tenant_id=other.id, work_type="height", zone_text="чужая", status="draft")
        session.add(wp)
        await session.commit()
        foreign_id = str(wp.id)
    assert (await async_client.get(f"{BASE}/{foreign_id}", headers=headers)).status_code == status.HTTP_404_NOT_FOUND
    listed = await async_client.get(BASE, headers=headers)
    assert all(item["id"] != foreign_id for item in listed.json()["items"])
```

- [ ] **Step 2: Run, confirm it fails** (404 — route not registered):

`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/api/test_work_permits_api.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`

- [ ] **Step 3: Write the schemas**

```python
# backend/app/schemas/work_permit.py
"""Schemas for work permits (наряды-допуски)."""
from __future__ import annotations

from datetime import datetime

from pydantic import field_validator

from app.domains.work_permits import lifecycle as lc
from app.schemas.base import BaseSchema


class WorkPermitMemberCreate(BaseSchema):
    person_id: str
    role: str

    @field_validator("role")
    @classmethod
    def _role(cls, v: str) -> str:
        if not lc.is_member_role(v):
            raise ValueError(f"invalid role: {v!r}")
        return v


class WorkPermitMemberRead(BaseSchema):
    id: str
    person_id: str
    role: str
    created_at: datetime


class WorkPermitEventRead(BaseSchema):
    id: str
    event_type: str
    at: datetime
    actor_user_id: str | None
    photo_file_id: str | None
    note: str | None


class WorkPermitCreate(BaseSchema):
    work_type: str
    zone_text: str
    number: str | None = None
    site_id: str | None = None
    equipment_text: str | None = None
    hazards_text: str | None = None
    measures_text: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None

    @field_validator("work_type")
    @classmethod
    def _work_type(cls, v: str) -> str:
        if not lc.is_work_type(v):
            raise ValueError(f"invalid work_type: {v!r}")
        return v


class WorkPermitUpdate(BaseSchema):
    work_type: str | None = None
    zone_text: str | None = None
    number: str | None = None
    site_id: str | None = None
    equipment_text: str | None = None
    hazards_text: str | None = None
    measures_text: str | None = None
    planned_start: datetime | None = None
    planned_end: datetime | None = None

    @field_validator("work_type")
    @classmethod
    def _work_type(cls, v: str | None) -> str | None:
        if v is not None and not lc.is_work_type(v):
            raise ValueError(f"invalid work_type: {v!r}")
        return v


class WorkPermitRead(BaseSchema):
    id: str
    number: str | None
    work_type: str
    zone_text: str
    site_id: str | None
    equipment_text: str | None
    hazards_text: str | None
    measures_text: str | None
    planned_start: datetime | None
    planned_end: datetime | None
    status: str
    opened_at: datetime | None
    closed_at: datetime | None
    suspended_at: datetime | None
    members: list[WorkPermitMemberRead]
    created_at: datetime
    updated_at: datetime


class WorkPermitPage(BaseSchema):
    items: list[WorkPermitRead]
    total: int


class WorkPermitActionRequest(BaseSchema):
    photo_file_id: str | None = None
    note: str | None = None


class WorkPermitExtendRequest(BaseSchema):
    planned_end: datetime


class ViolationRead(BaseSchema):
    person_id: str
    role: str
    code: str
    severity: str


class ReadinessReportRead(BaseSchema):
    ok: bool
    violations: list[ViolationRead]
```

- [ ] **Step 4: Write the routes (CRUD + members)** `backend/app/api/routes/work_permits.py`:

```python
# backend/app/api/routes/work_permits.py
"""Endpoints for work permits (наряды-допуски)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.work_permits import lifecycle as lc
from app.domains.work_permits import (
    add_member, create_work_permit, delete_draft, list_events, list_members,
    remove_member, update_work_permit,
)
from app.models.models import Person
from app.models.tenanting import Tenant
from app.models.work_permit import WorkPermit
from app.schemas.work_permit import (
    WorkPermitCreate, WorkPermitMemberCreate, WorkPermitMemberRead, WorkPermitPage,
    WorkPermitRead, WorkPermitUpdate,
)

router = APIRouter(prefix="/work-permits")

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_READ_ROLES = ["admin"]
_WRITE_ROLES = ["admin"]
ReaderAccess = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_READ_ROLES))]
WriterAccess = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_WRITE_ROLES))]


def _transition_conflict(exc: lc.WorkPermitTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="WORK_PERMIT_TRANSITION_INVALID", message=str(exc), error_type="work_permit"
        ),
    )


def _member_schema(m) -> WorkPermitMemberRead:
    return WorkPermitMemberRead(id=str(m.id), person_id=str(m.person_id), role=m.role, created_at=m.created_at)


async def _permit_read(session: AsyncSession, tenant: Tenant, wp: WorkPermit) -> WorkPermitRead:
    members = await list_members(session, tenant_id=tenant.id, work_permit_id=wp.id)
    return WorkPermitRead(
        id=str(wp.id), number=wp.number, work_type=wp.work_type, zone_text=wp.zone_text,
        site_id=str(wp.site_id) if wp.site_id else None, equipment_text=wp.equipment_text,
        hazards_text=wp.hazards_text, measures_text=wp.measures_text,
        planned_start=wp.planned_start, planned_end=wp.planned_end, status=str(wp.status),
        opened_at=wp.opened_at, closed_at=wp.closed_at, suspended_at=wp.suspended_at,
        members=[_member_schema(m) for m in members],
        created_at=wp.created_at, updated_at=wp.updated_at,
    )


async def _get_or_404(session: AsyncSession, tenant: Tenant, wp_id: str) -> WorkPermit:
    stmt = select(WorkPermit).where(WorkPermit.id == wp_id, WorkPermit.tenant_id == tenant.id)
    wp = (await session.execute(stmt)).scalar_one_or_none()
    if wp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "work permit not found")
    return wp


async def _ensure_person(session: AsyncSession, tenant: Tenant, person_id: str) -> None:
    stmt = select(Person.id).where(
        Person.id == person_id, Person.tenant_id == tenant.id, Person.deleted_at.is_(None)
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found")


async def _ensure_file(session: AsyncSession, tenant: Tenant, file_id: str) -> None:
    from app.models.file import File
    stmt = select(File.id).where(File.id == file_id, File.tenant_id == tenant.id)
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "file not found")


@router.get("", response_model=WorkPermitPage)
async def list_work_permits(
    tenant: TenantDep, session: SessionDep, access: ReaderAccess,
    status_filter: str | None = Query(None, alias="status"),
    site_id: str | None = None, work_type: str | None = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
) -> WorkPermitPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = select(WorkPermit).where(WorkPermit.tenant_id == tenant.id)
    count_stmt = select(func.count()).select_from(WorkPermit).where(WorkPermit.tenant_id == tenant.id)
    for col, val in (("status", status_filter), ("site_id", site_id), ("work_type", work_type)):
        if val:
            stmt = stmt.where(getattr(WorkPermit, col) == val)
            count_stmt = count_stmt.where(getattr(WorkPermit, col) == val)
    stmt = stmt.order_by(WorkPermit.created_at.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    total = (await session.execute(count_stmt)).scalar_one()
    items = [await _permit_read(session, tenant, wp) for wp in rows]
    return WorkPermitPage(items=items, total=total)


@router.post("", response_model=WorkPermitRead, status_code=status.HTTP_201_CREATED)
@audit_operation("create", "work_permit")
async def create_work_permit_endpoint(
    payload: WorkPermitCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    wp = await create_work_permit(
        session, tenant_id=tenant.id, work_type=payload.work_type, zone_text=payload.zone_text,
        number=payload.number, site_id=payload.site_id, equipment_text=payload.equipment_text,
        hazards_text=payload.hazards_text, measures_text=payload.measures_text,
        planned_start=payload.planned_start, planned_end=payload.planned_end,
    )
    return await _permit_read(session, tenant, wp)


@router.get("/{wp_id}", response_model=WorkPermitRead)
async def get_work_permit(wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _permit_read(session, tenant, await _get_or_404(session, tenant, wp_id))


@router.patch("/{wp_id}", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def update_work_permit_endpoint(
    wp_id: str, payload: WorkPermitUpdate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    fields = payload.model_dump(exclude_unset=True)
    if "site_id" in fields and fields["site_id"]:
        from app.models.models import Site
        ok = (await session.execute(select(Site.id).where(
            Site.id == fields["site_id"], Site.tenant_id == tenant.id, Site.deleted_at.is_(None)
        ))).scalar_one_or_none()
        if ok is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "site not found")
    try:
        wp = await update_work_permit(session, tenant_id=tenant.id, work_permit_id=wp_id, **fields)
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    return await _permit_read(session, tenant, wp)


@router.delete("/{wp_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("delete", "work_permit")
async def delete_work_permit_endpoint(wp_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    try:
        await delete_draft(session, tenant_id=tenant.id, work_permit_id=wp_id)
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    from fastapi import Response
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{wp_id}/members", response_model=WorkPermitMemberRead, status_code=status.HTTP_201_CREATED)
@audit_operation("update", "work_permit")
async def add_member_endpoint(
    wp_id: str, payload: WorkPermitMemberCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess
) -> WorkPermitMemberRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    await _ensure_person(session, tenant, payload.person_id)
    try:
        member = await add_member(
            session, tenant_id=tenant.id, work_permit_id=wp_id,
            person_id=payload.person_id, role=payload.role,
        )
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    return _member_schema(member)


@router.delete("/{wp_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
@audit_operation("update", "work_permit")
async def remove_member_endpoint(
    wp_id: str, member_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess
):
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    ok = await remove_member(session, tenant_id=tenant.id, work_permit_id=wp_id, member_id=member_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "member not found")
    from fastapi import Response
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 5: Register the router** in `backend/app/api/v1/route_groups.py` — add `work_permits,` to the `from app.api.routes import (...)` block (alphabetical, near `work...`/end), and add `(work_permits.router, {"tags": ["work-permits"]}),` to the same registration list where `(ppe.router, ...)` / `(permits.router, ...)` appear.

- [ ] **Step 6: Run the CRUD/members API test, confirm PASS** (4 passed):

`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/api/test_work_permits_api.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/work_permit.py backend/app/api/routes/work_permits.py backend/app/api/v1/route_groups.py tests/api/test_work_permits_api.py
git commit -m "feat(work-permits): schemas + CRUD/members API + router wiring"
```

---

## Task 6: Действия API (issue/suspend/resume/close/cancel/extend) + readiness + events

**Files:**
- Modify: `backend/app/api/routes/work_permits.py` (add action endpoints)
- Test: `tests/api/test_work_permits_api.py` (append action tests)

- [ ] **Step 1: Append the failing action tests**

```python
# append to tests/api/test_work_permits_api.py
@pytest.mark.asyncio
async def test_issue_blocked_then_allowed_with_permit(async_client, make_auth_headers, data_factory, sessionmaker):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    person = await data_factory.create_person()
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    await async_client.post(f"{BASE}/{wp_id}/members", headers=headers, json={"person_id": str(person.id), "role": "foreman"})

    # no personal permit yet → readiness not ok, issue 409 WORK_PERMIT_BLOCKED
    rd = await async_client.get(f"{BASE}/{wp_id}/readiness", headers=headers)
    assert rd.status_code == status.HTTP_200_OK and rd.json()["ok"] is False
    blocked = await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    assert blocked.status_code == status.HTTP_409_CONFLICT

    # seed an active personal permit, then issue succeeds
    from datetime import date as _date, timedelta as _td
    from app.domains.permits import service as permit_svc
    async with sessionmaker() as session:
        await permit_svc.create_permit(
            session, tenant_id=person.tenant_id, person_id=person.id, permit_type="height",
            issued_at=_date.today(), valid_until=_date.today() + _td(days=30),
        )
        await session.commit()

    ok = await async_client.post(f"{BASE}/{wp_id}/issue", headers=headers, json={})
    assert ok.status_code == status.HTTP_200_OK, ok.text
    assert ok.json()["status"] == "issued"

    # suspend → resume → close, events recorded
    assert (await async_client.post(f"{BASE}/{wp_id}/suspend", headers=headers, json={})).json()["status"] == "suspended"
    assert (await async_client.post(f"{BASE}/{wp_id}/resume", headers=headers, json={})).json()["status"] == "issued"
    assert (await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})).json()["status"] == "closed"

    ev = await async_client.get(f"{BASE}/{wp_id}/events", headers=headers)
    assert [e["event_type"] for e in ev.json()] == ["issued", "suspended", "resumed", "closed"]


@pytest.mark.asyncio
async def test_close_from_draft_409(async_client, make_auth_headers, data_factory):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    r = await async_client.post(BASE, headers=headers, json={"work_type": "height", "zone_text": "z"})
    wp_id = r.json()["id"]
    bad = await async_client.post(f"{BASE}/{wp_id}/close", headers=headers, json={})
    assert bad.status_code == status.HTTP_409_CONFLICT
```

- [ ] **Step 2: Run, confirm it fails** (404 on action endpoints):

`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/api/test_work_permits_api.py -k "issue or close_from_draft" -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`

- [ ] **Step 3: Add action + readiness + events endpoints** to `backend/app/api/routes/work_permits.py`. First add imports near the top:

```python
from app.domains.work_permits import cancel, close, extend, issue, resume, suspend
from app.services.work_permit_admission import (
    WorkPermitBlocked, check_brigade_readiness,
)
from app.schemas.work_permit import (
    ReadinessReportRead, ViolationRead, WorkPermitActionRequest,
    WorkPermitEventRead, WorkPermitExtendRequest,
)
```

Then append the endpoints:

```python
def _blocked_conflict(exc: WorkPermitBlocked) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="WORK_PERMIT_BLOCKED",
            message="brigade readiness failed",
            error_type="work_permit",
            details={"violations": [
                {"person_id": v.person_id, "role": v.role, "code": v.code, "severity": v.severity}
                for v in exc.violations
            ]},
        ),
    )


async def _action(session, tenant, wp_id, coro_factory):
    await _get_or_404(session, tenant, wp_id)
    try:
        wp = await coro_factory()
    except lc.WorkPermitTransitionError as exc:
        raise _transition_conflict(exc) from exc
    except WorkPermitBlocked as exc:
        raise _blocked_conflict(exc) from exc
    return await _permit_read(session, tenant, wp)


@router.get("/{wp_id}/readiness", response_model=ReadinessReportRead)
async def readiness(wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> ReadinessReportRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    report = await check_brigade_readiness(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return ReadinessReportRead(
        ok=report.ok,
        violations=[ViolationRead(person_id=v.person_id, role=v.role, code=v.code, severity=v.severity)
                    for v in report.violations],
    )


@router.get("/{wp_id}/events", response_model=list[WorkPermitEventRead])
async def events(wp_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> list[WorkPermitEventRead]:
    TenantContextValidator.ensure_tenant_context(tenant)
    await _get_or_404(session, tenant, wp_id)
    rows = await list_events(session, tenant_id=tenant.id, work_permit_id=wp_id)
    return [WorkPermitEventRead(
        id=str(e.id), event_type=e.event_type, at=e.at, actor_user_id=e.actor_user_id,
        photo_file_id=e.photo_file_id, note=e.note,
    ) for e in rows]


@router.post("/{wp_id}/issue", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def issue_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.photo_file_id:
        await _ensure_file(session, tenant, payload.photo_file_id)
    return await _action(session, tenant, wp_id, lambda: issue(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None,
        photo_file_id=payload.photo_file_id, note=payload.note,
    ))


@router.post("/{wp_id}/suspend", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def suspend_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: suspend(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None, note=payload.note,
    ))


@router.post("/{wp_id}/resume", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def resume_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: resume(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None, note=payload.note,
    ))


@router.post("/{wp_id}/close", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def close_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.photo_file_id:
        await _ensure_file(session, tenant, payload.photo_file_id)
    return await _action(session, tenant, wp_id, lambda: close(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None,
        photo_file_id=payload.photo_file_id, note=payload.note,
    ))


@router.post("/{wp_id}/cancel", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def cancel_endpoint(wp_id: str, payload: WorkPermitActionRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: cancel(
        session, tenant_id=tenant.id, work_permit_id=wp_id,
        actor_user_id=access.user.id if access else None, note=payload.note,
    ))


@router.post("/{wp_id}/extend", response_model=WorkPermitRead)
@audit_operation("update", "work_permit")
async def extend_endpoint(wp_id: str, payload: WorkPermitExtendRequest, tenant: TenantDep, session: SessionDep, access: WriterAccess) -> WorkPermitRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    return await _action(session, tenant, wp_id, lambda: extend(
        session, tenant_id=tenant.id, work_permit_id=wp_id, planned_end=payload.planned_end,
        actor_user_id=access.user.id if access else None,
    ))
```

(`api_problem_detail` signature confirmed: it accepts `details: dict[str, Any]` — the `violations` list is nested under `details` and surfaced in the response body by the error handlers.)

- [ ] **Step 4: Run the full API test file, confirm PASS:**

`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest tests/api/test_work_permits_api.py -p no:xdist --timeout=600 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"`
Expected: all PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/work_permits.py tests/api/test_work_permits_api.py
git commit -m "feat(work-permits): action endpoints (issue/suspend/resume/close/cancel/extend) + readiness + events"
```

---

## Task 7: Контурная регрессия + handoff

- [ ] **Step 1: Run the full work-permits cohort**

```
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest backend/tests/test_work_permit_lifecycle.py backend/tests/test_wp01_work_permit_migration.py tests/test_work_permit_service.py tests/test_work_permit_admission.py tests/api/test_work_permits_api.py -p no:xdist --timeout=900 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"
```
Expected: all PASS. Record the `N passed` summary and any Py3.12-vs-3.13 mismatch (do not abort).

- [ ] **Step 2: Clean up temp files**

```bash
rm -f _t.txt
```

- [ ] **Step 3: Update the handoff report** — prepend a new `## Last Agent Handoff (2026-06-16, КОНТУР «НАРЯДЫ-ДОПУСКИ» §16 Срез-2 ...)` section to `AI_IMPLEMENTATION_REPORT.md` (mirror the prior entries' format): models/migration `wp01`, FSM, gate, mobile open/close+photo, endpoints, tests, deferred Срез-3 items (templates, checklists, catalogs, file upload, frontend, permit auto-expiry).

- [ ] **Step 4: Commit**

```bash
git add AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(report): handoff — наряд-допуск §16 Срез-2 complete (wp01 + gate + actions)"
```
