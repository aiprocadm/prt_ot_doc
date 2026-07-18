# P10-01 Комитеты — Срез-1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a срез-1 skeleton for the committees/commissions/meetings module (TZ B.17 / vNext §18): committee → meeting → agenda → decision → decision-task, with backend CRUD API (ETag + tenant isolation + lifecycle guards) behind a default-off feature flag, plus a thin list/detail UI.

**Architecture:** New isolated bounded context `committees`. ORM models in a new `backend/app/models/committees.py` (NOT the 3000-line `models.py`); pure-function lifecycle in `backend/app/domains/committees/lifecycle.py`; Pydantic schemas in `backend/app/schemas/committees.py`; FastAPI routes in `backend/app/api/routes/committees.py` registered via `route_groups.py`; additive migration `cmt01`. Frontend: one page + api/store slice gated on the flag.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 async / Alembic / Pydantic v2 (backend); React + Vite + TypeScript (frontend). Tests: pytest, mocking `session` at the route boundary (repo convention — no live DB).

**Test command convention (per CLAUDE.md + memory):** run on Py3.12 if present, else fallback and note mismatch. On Windows prefer PowerShell→file redirect. Canonical example:
`python3.12 -m pytest backend/tests/test_committees_lifecycle.py -v` (fallback: `python -m pytest ...`).

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `backend/app/models/committees.py` | 6 ORM models + 4 enums (new module) | 1 |
| `backend/app/models/__init__.py` | register the new module (import) | 1 |
| `backend/app/migrations/versions/20260625_cmt01_committees.py` | additive DDL for 6 tables | 2 |
| `backend/app/domains/committees/__init__.py` | domain package exports | 3 |
| `backend/app/domains/committees/lifecycle.py` | pure meeting-transition + overdue logic | 3 |
| `backend/app/schemas/committees.py` | Pydantic request/response schemas | 4 |
| `backend/app/domains/committees/service.py` | tenant-scoped query/mutation helpers | 5 |
| `backend/app/api/routes/committees.py` | HTTP endpoints | 6 |
| `backend/app/api/v1/route_groups.py` | register router | 6 |
| `frontend/src/api/committees.ts` | API client | 8 |
| `frontend/src/store/committees.ts` | store slice | 8 |
| `frontend/src/pages/committees/CommitteesPage.tsx` | thin list/detail UI | 8 |
| `docs/audit/TZ_COVERAGE_MATRIX.md` / roadmap reconciliation | status → partial | 9 |
| `CHANGELOG.md` | entry | 9 |

Tests live in `backend/tests/test_committees_*.py` (flat, repo convention).

---

## Task 1: ORM models + enums

**Files:**
- Create: `backend/app/models/committees.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_committees_models.py`

- [ ] **Step 1: Write the failing model-shape test**

Create `backend/tests/test_committees_models.py`:

```python
"""Pin: committees срез-1 model shapes (P10-01 / TZ B.17)."""
from __future__ import annotations


def test_committee_table_and_columns() -> None:
    from app.models.committees import Committee

    assert Committee.__tablename__ == "committee"
    cols = set(Committee.__table__.columns.keys())
    assert {
        "id", "tenant_id", "version", "created_at", "updated_at", "deleted_at",
        "kind", "name", "description", "is_active",
    } <= cols


def test_meeting_table_and_columns() -> None:
    from app.models.committees import CommitteeMeeting

    assert CommitteeMeeting.__tablename__ == "committee_meeting"
    cols = set(CommitteeMeeting.__table__.columns.keys())
    assert {
        "id", "tenant_id", "deleted_at", "committee_id",
        "scheduled_at", "location", "status",
    } <= cols


def test_child_tables_and_columns() -> None:
    from app.models.committees import (
        CommitteeMember,
        CommitteeAgendaItem,
        CommitteeDecision,
        CommitteeDecisionTask,
    )

    assert CommitteeMember.__tablename__ == "committee_member"
    assert {"committee_id", "person_id", "role"} <= set(
        CommitteeMember.__table__.columns.keys()
    )
    assert CommitteeAgendaItem.__tablename__ == "committee_agenda_item"
    assert {"meeting_id", "seq", "title", "presenter_person_id"} <= set(
        CommitteeAgendaItem.__table__.columns.keys()
    )
    assert CommitteeDecision.__tablename__ == "committee_decision"
    assert {"meeting_id", "agenda_item_id", "text", "decided_at"} <= set(
        CommitteeDecision.__table__.columns.keys()
    )
    assert CommitteeDecisionTask.__tablename__ == "committee_decision_task"
    assert {
        "decision_id", "assignee_person_id", "due_date", "status", "evidence_note",
    } <= set(CommitteeDecisionTask.__table__.columns.keys())


def test_enums_use_value_labels() -> None:
    from app.models.committees import (
        CommitteeKind,
        CommitteeMemberRole,
        MeetingStatus,
        DecisionTaskStatus,
    )

    assert CommitteeKind.OSMS.value == "osms"
    assert CommitteeMemberRole.CHAIR.value == "chair"
    assert MeetingStatus.PLANNED.value == "planned"
    assert DecisionTaskStatus.OPEN.value == "open"


def test_models_reexported_from_package() -> None:
    from app.models import Committee, CommitteeMeeting  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_committees_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models.committees'`.

- [ ] **Step 3: Create the models module**

Create `backend/app/models/committees.py`:

```python
"""Committees / commissions / meetings ORM models (P10-01 срез-1, TZ B.17).

Bounded context kept OUT of the 3000-line ``models.py`` to avoid the
duplicate-class hazards documented there. Native enums use the project
``native_enum`` helper (``.value`` labels, explicit ``name=``) per
enum-pg-label-parity discipline.
"""
from __future__ import annotations

import enum
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum


class CommitteeKind(str, enum.Enum):
    OSMS = "osms"  # комитет по ОТ
    PB = "pb"  # комитет по ПБ
    COMMISSION_TRAINING = "commission_training"
    COMMISSION_INVESTIGATION = "commission_investigation"
    OTHER = "other"


class CommitteeMemberRole(str, enum.Enum):
    CHAIR = "chair"
    SECRETARY = "secretary"
    MEMBER = "member"


class MeetingStatus(str, enum.Enum):
    PLANNED = "planned"
    HELD = "held"
    CANCELLED = "cancelled"


class DecisionTaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    OVERDUE = "overdue"  # stored value reserved; срез-1 computes overdue at read


class Committee(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "committee"

    kind: Mapped[CommitteeKind] = mapped_column(
        native_enum(CommitteeKind, name="committeekind"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class CommitteeMember(TenantBaseModel):
    __tablename__ = "committee_member"

    committee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("committee.id"), nullable=False, index=True
    )
    person_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[CommitteeMemberRole] = mapped_column(
        native_enum(CommitteeMemberRole, name="committeememberrole"), nullable=False
    )


class CommitteeMeeting(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "committee_meeting"

    committee_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("committee.id"), nullable=False, index=True
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[MeetingStatus] = mapped_column(
        native_enum(MeetingStatus, name="meetingstatus"),
        nullable=False,
        default=MeetingStatus.PLANNED,
    )


class CommitteeAgendaItem(TenantBaseModel):
    __tablename__ = "committee_agenda_item"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("committee_meeting.id"), nullable=False, index=True
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    presenter_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class CommitteeDecision(TenantBaseModel):
    __tablename__ = "committee_decision"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("committee_meeting.id"), nullable=False, index=True
    )
    agenda_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("committee_agenda_item.id"), nullable=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now().astimezone(),
        nullable=False,
    )


class CommitteeDecisionTask(TenantBaseModel):
    __tablename__ = "committee_decision_task"

    decision_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("committee_decision.id"), nullable=False, index=True
    )
    assignee_person_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[DecisionTaskStatus] = mapped_column(
        native_enum(DecisionTaskStatus, name="decisiontaskstatus"),
        nullable=False,
        default=DecisionTaskStatus.OPEN,
    )
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: Register the module in the model package**

Modify `backend/app/models/__init__.py` — add after the existing `from app.models.calendar_views import ...` line (keep alphabetical-ish grouping with the other domain modules):

```python
from app.models.committees import (
    Committee,
    CommitteeAgendaItem,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeKind,
    CommitteeMeeting,
    CommitteeMember,
    CommitteeMemberRole,
    DecisionTaskStatus,
    MeetingStatus,
)
```

Then add those names to the module's `__all__` list if one is present (append the 10 names).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_committees_models.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Run the ORM mapper-config guard (catches duplicate-class / relationship breakage)**

Run: `python -m pytest backend/tests/test_orm_mapper_configuration.py -v`
Expected: PASS (new models do not break `configure_mappers()`).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/committees.py backend/app/models/__init__.py backend/tests/test_committees_models.py
git commit -m "feat(committees): срез-1 ORM models + enums (P10-01)"
```

---

## Task 2: Additive migration `cmt01`

**Files:**
- Create: `backend/app/migrations/versions/20260625_cmt01_committees.py`
- Test: `backend/tests/test_cmt01_committees_migration.py`

- [ ] **Step 1: Write the failing migration test**

Create `backend/tests/test_cmt01_committees_migration.py`:

```python
"""Pin: cmt01 committees migration shape (P10-01)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260625_cmt01_committees.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("cmt01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260625_cmt01_committees"
    assert mod.down_revision == "20260623_cm01_company_status_tags_person_position"


def test_upgrade_downgrade_callable() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_file_creates_six_tables() -> None:
    text = _MIGRATION.read_text(encoding="utf-8")
    for table in (
        "committee",
        "committee_member",
        "committee_meeting",
        "committee_agenda_item",
        "committee_decision",
        "committee_decision_task",
    ):
        assert f'"{table}"' in text, f"missing create_table for {table}"
    # honest downgrade drops every table it created
    assert text.count("op.drop_table") == 6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_cmt01_committees_migration.py -v`
Expected: FAIL — migration file does not exist.

- [ ] **Step 3: Write the migration**

Create `backend/app/migrations/versions/20260625_cmt01_committees.py`. Table names are LITERAL (AST-audit blindspot). Children dropped before parents in downgrade (FK-before-table lesson).

```python
"""cmt01: committees срез-1 — 6 tables (additive, P10-01 / TZ B.17).

committee / committee_member / committee_meeting / committee_agenda_item /
committee_decision / committee_decision_task. Native enums созданы с .value
лейблами (enum-pg-label-parity). Honest downgrade удаляет таблицы и enum-типы
в обратном (child→parent) порядке.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260625_cmt01_committees"
down_revision = "20260623_cm01_company_status_tags_person_position"
branch_labels = None
depends_on = None


_COMMITTEE_KIND = sa.Enum(
    "osms", "pb", "commission_training", "commission_investigation", "other",
    name="committeekind",
)
_MEMBER_ROLE = sa.Enum("chair", "secretary", "member", name="committeememberrole")
_MEETING_STATUS = sa.Enum("planned", "held", "cancelled", name="meetingstatus")
_TASK_STATUS = sa.Enum("open", "in_progress", "done", "overdue", name="decisiontaskstatus")


def _common(*extra: sa.Column) -> list[sa.Column]:
    """id + tenant base + timestamps + version columns shared by every table."""
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        *extra,
    ]


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (_COMMITTEE_KIND, _MEMBER_ROLE, _MEETING_STATUS, _TASK_STATUS):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "committee",
        *_common(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("kind", _COMMITTEE_KIND, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        ),
    )
    op.create_table(
        "committee_member",
        *_common(
            sa.Column("committee_id", sa.String(length=36), sa.ForeignKey("committee.id"), nullable=False, index=True),
            sa.Column("person_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("role", _MEMBER_ROLE, nullable=False),
        ),
    )
    op.create_table(
        "committee_meeting",
        *_common(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("committee_id", sa.String(length=36), sa.ForeignKey("committee.id"), nullable=False, index=True),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("status", _MEETING_STATUS, nullable=False, server_default="planned"),
        ),
    )
    op.create_table(
        "committee_agenda_item",
        *_common(
            sa.Column("meeting_id", sa.String(length=36), sa.ForeignKey("committee_meeting.id"), nullable=False, index=True),
            sa.Column("seq", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column("presenter_person_id", sa.String(length=36), nullable=True),
        ),
    )
    op.create_table(
        "committee_decision",
        *_common(
            sa.Column("meeting_id", sa.String(length=36), sa.ForeignKey("committee_meeting.id"), nullable=False, index=True),
            sa.Column("agenda_item_id", sa.String(length=36), sa.ForeignKey("committee_agenda_item.id"), nullable=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        ),
    )
    op.create_table(
        "committee_decision_task",
        *_common(
            sa.Column("decision_id", sa.String(length=36), sa.ForeignKey("committee_decision.id"), nullable=False, index=True),
            sa.Column("assignee_person_id", sa.String(length=36), nullable=True),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", _TASK_STATUS, nullable=False, server_default="open"),
            sa.Column("evidence_note", sa.Text(), nullable=True),
        ),
    )


def downgrade() -> None:
    op.drop_table("committee_decision_task")
    op.drop_table("committee_decision")
    op.drop_table("committee_agenda_item")
    op.drop_table("committee_meeting")
    op.drop_table("committee_member")
    op.drop_table("committee")
    bind = op.get_bind()
    for enum_type in (_TASK_STATUS, _MEETING_STATUS, _MEMBER_ROLE, _COMMITTEE_KIND):
        enum_type.drop(bind, checkfirst=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_cmt01_committees_migration.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Verify alembic can load the revision graph (no duplicate-revision / cycle)**

Run: `python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; ScriptDirectory.from_config(Config('backend/alembic.ini')).walk_revisions()"`
Expected: no exception. (If `alembic.ini` path differs, locate with `git ls-files | grep alembic.ini` and use that path.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260625_cmt01_committees.py backend/tests/test_cmt01_committees_migration.py
git commit -m "feat(committees): cmt01 additive migration for 6 срез-1 tables"
```

---

## Task 3: Lifecycle (pure functions)

**Files:**
- Create: `backend/app/domains/committees/__init__.py`
- Create: `backend/app/domains/committees/lifecycle.py`
- Test: `backend/tests/test_committees_lifecycle.py`

- [ ] **Step 1: Write the failing lifecycle test**

Create `backend/tests/test_committees_lifecycle.py`:

```python
"""Unit: committees lifecycle guards + overdue computation (P10-01)."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.committees.lifecycle import (
    MeetingTransitionError,
    validate_meeting_transition,
    ensure_meeting_held,
    is_task_overdue,
)
from app.models.committees import MeetingStatus, DecisionTaskStatus

TODAY = date(2026, 6, 25)


def test_planned_to_held_allowed():
    validate_meeting_transition(MeetingStatus.PLANNED, MeetingStatus.HELD)


def test_planned_to_cancelled_allowed():
    validate_meeting_transition(MeetingStatus.PLANNED, MeetingStatus.CANCELLED)


def test_held_to_cancelled_allowed():
    validate_meeting_transition(MeetingStatus.HELD, MeetingStatus.CANCELLED)


def test_held_to_planned_rejected():
    with pytest.raises(MeetingTransitionError):
        validate_meeting_transition(MeetingStatus.HELD, MeetingStatus.PLANNED)


def test_cancelled_is_terminal():
    with pytest.raises(MeetingTransitionError):
        validate_meeting_transition(MeetingStatus.CANCELLED, MeetingStatus.HELD)


def test_decision_requires_held_meeting():
    ensure_meeting_held(MeetingStatus.HELD)  # no raise
    with pytest.raises(MeetingTransitionError):
        ensure_meeting_held(MeetingStatus.PLANNED)


def test_overdue_true_when_past_due_and_open():
    assert is_task_overdue(DecisionTaskStatus.OPEN, TODAY - timedelta(days=1), TODAY) is True


def test_overdue_false_when_done():
    assert is_task_overdue(DecisionTaskStatus.DONE, TODAY - timedelta(days=5), TODAY) is False


def test_overdue_false_when_no_due_date():
    assert is_task_overdue(DecisionTaskStatus.OPEN, None, TODAY) is False


def test_overdue_false_when_due_today():
    assert is_task_overdue(DecisionTaskStatus.OPEN, TODAY, TODAY) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_committees_lifecycle.py -v`
Expected: FAIL — `ModuleNotFoundError: app.domains.committees.lifecycle`.

- [ ] **Step 3: Write the lifecycle module + package init**

Create `backend/app/domains/committees/__init__.py`:

```python
"""Committees bounded context (P10-01 срез-1)."""
from app.domains.committees.lifecycle import (
    MeetingTransitionError,
    ensure_meeting_held,
    is_task_overdue,
    validate_meeting_transition,
)

__all__ = [
    "MeetingTransitionError",
    "ensure_meeting_held",
    "is_task_overdue",
    "validate_meeting_transition",
]
```

Create `backend/app/domains/committees/lifecycle.py`:

```python
"""Pure-function lifecycle rules for committees срез-1.

No DB access — callers pass current/target states. Mirrors the
work_permits/ppe lifecycle style (raise a typed error; route maps to 409).
"""
from __future__ import annotations

from datetime import date

from app.models.committees import DecisionTaskStatus, MeetingStatus

#: Allowed meeting status transitions.
_ALLOWED: dict[MeetingStatus, set[MeetingStatus]] = {
    MeetingStatus.PLANNED: {MeetingStatus.HELD, MeetingStatus.CANCELLED},
    MeetingStatus.HELD: {MeetingStatus.CANCELLED},
    MeetingStatus.CANCELLED: set(),
}


class MeetingTransitionError(ValueError):
    """Raised on an illegal meeting transition or decision-on-non-held."""


def validate_meeting_transition(current: MeetingStatus, target: MeetingStatus) -> None:
    if target not in _ALLOWED.get(current, set()):
        raise MeetingTransitionError(
            f"Cannot transition meeting {current.value} -> {target.value}"
        )


def ensure_meeting_held(status: MeetingStatus) -> None:
    if status is not MeetingStatus.HELD:
        raise MeetingTransitionError(
            f"Decisions allowed only on a held meeting (status={status.value})"
        )


def is_task_overdue(
    status: DecisionTaskStatus, due_date: date | None, today: date
) -> bool:
    """A task is overdue when it has a past due_date and is not done."""
    if due_date is None or status is DecisionTaskStatus.DONE:
        return False
    return due_date < today
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_committees_lifecycle.py -v`
Expected: PASS (10 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/committees/ backend/tests/test_committees_lifecycle.py
git commit -m "feat(committees): lifecycle guards + overdue computation"
```

---

## Task 4: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/committees.py`
- Test: `backend/tests/test_committees_schemas.py`

- [ ] **Step 1: Write the failing schema test**

Create `backend/tests/test_committees_schemas.py`:

```python
"""Unit: committees schemas round-trip + overdue projection (P10-01)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from app.schemas.committees import (
    CommitteeCreate,
    CommitteeRead,
    MeetingCreate,
    MeetingStatusUpdate,
    AgendaItemCreate,
    DecisionCreate,
    DecisionTaskCreate,
    DecisionTaskRead,
    DecisionTaskUpdate,
)
from app.models.committees import CommitteeKind, MeetingStatus, DecisionTaskStatus


def test_committee_create_defaults():
    c = CommitteeCreate(kind=CommitteeKind.OSMS, name="Комитет ОТ")
    assert c.is_active is True
    assert c.description is None


def test_meeting_create_requires_scheduled_at():
    m = MeetingCreate(scheduled_at=datetime(2026, 7, 1, tzinfo=timezone.utc))
    assert m.location is None


def test_meeting_status_update_enum():
    u = MeetingStatusUpdate(status=MeetingStatus.HELD)
    assert u.status is MeetingStatus.HELD


def test_decision_task_read_carries_overdue_flag():
    t = DecisionTaskRead(
        id="t1",
        decision_id="d1",
        assignee_person_id=None,
        due_date=date(2026, 6, 1),
        status=DecisionTaskStatus.OPEN,
        evidence_note=None,
        is_overdue=True,
    )
    assert t.is_overdue is True


def test_decision_task_update_partial():
    u = DecisionTaskUpdate(status=DecisionTaskStatus.DONE)
    assert u.evidence_note is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_committees_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: app.schemas.committees`.

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/committees.py`:

```python
"""Pydantic schemas for committees срез-1 (P10-01)."""
from __future__ import annotations

from datetime import date, datetime

from app.models.committees import (
    CommitteeKind,
    CommitteeMemberRole,
    DecisionTaskStatus,
    MeetingStatus,
)
from app.schemas.base import BaseSchema


# --- Committee ---
class CommitteeCreate(BaseSchema):
    kind: CommitteeKind
    name: str
    description: str | None = None
    is_active: bool = True


class CommitteeUpdate(BaseSchema):
    kind: CommitteeKind | None = None
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None


class CommitteeRead(BaseSchema):
    id: str
    kind: CommitteeKind
    name: str
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


class CommitteePage(BaseSchema):
    items: list[CommitteeRead]
    total: int
    limit: int
    offset: int


# --- Member ---
class MemberCreate(BaseSchema):
    person_id: str
    role: CommitteeMemberRole = CommitteeMemberRole.MEMBER


class MemberRead(BaseSchema):
    id: str
    committee_id: str
    person_id: str
    role: CommitteeMemberRole


# --- Meeting ---
class MeetingCreate(BaseSchema):
    scheduled_at: datetime
    location: str | None = None


class MeetingStatusUpdate(BaseSchema):
    status: MeetingStatus


class MeetingRead(BaseSchema):
    id: str
    committee_id: str
    scheduled_at: datetime
    location: str | None
    status: MeetingStatus
    created_at: datetime
    updated_at: datetime


class MeetingPage(BaseSchema):
    items: list[MeetingRead]
    total: int
    limit: int
    offset: int


# --- Agenda ---
class AgendaItemCreate(BaseSchema):
    title: str
    seq: int = 1
    presenter_person_id: str | None = None


class AgendaItemRead(BaseSchema):
    id: str
    meeting_id: str
    seq: int
    title: str
    presenter_person_id: str | None


# --- Decision ---
class DecisionCreate(BaseSchema):
    text: str
    agenda_item_id: str | None = None


class DecisionRead(BaseSchema):
    id: str
    meeting_id: str
    agenda_item_id: str | None
    text: str
    decided_at: datetime


# --- Decision task ---
class DecisionTaskCreate(BaseSchema):
    assignee_person_id: str | None = None
    due_date: date | None = None
    evidence_note: str | None = None


class DecisionTaskUpdate(BaseSchema):
    assignee_person_id: str | None = None
    due_date: date | None = None
    status: DecisionTaskStatus | None = None
    evidence_note: str | None = None


class DecisionTaskRead(BaseSchema):
    id: str
    decision_id: str
    assignee_person_id: str | None
    due_date: date | None
    status: DecisionTaskStatus
    evidence_note: str | None
    is_overdue: bool


# --- Protocol projection ---
class ProtocolDecision(BaseSchema):
    decision: DecisionRead
    tasks: list[DecisionTaskRead]


class ProtocolRead(BaseSchema):
    meeting: MeetingRead
    decisions: list[ProtocolDecision]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_committees_schemas.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/committees.py backend/tests/test_committees_schemas.py
git commit -m "feat(committees): pydantic schemas (срез-1)"
```

---

## Task 5: Domain service (tenant-scoped helpers)

**Files:**
- Create: `backend/app/domains/committees/service.py`
- Modify: `backend/app/domains/committees/__init__.py` (export helpers)
- Test: `backend/tests/test_committees_service.py`

The service holds the read-projection + overdue mapping so routes stay thin and the projection is unit-testable without HTTP.

- [ ] **Step 1: Write the failing service test**

Create `backend/tests/test_committees_service.py`:

```python
"""Unit: committees service projection helpers (P10-01)."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.domains.committees.service import task_to_read, build_protocol
from app.models.committees import DecisionTaskStatus, MeetingStatus

TODAY = date(2026, 6, 25)


def _task(**kw):
    base = dict(
        id="t1", decision_id="d1", assignee_person_id=None,
        due_date=None, status=DecisionTaskStatus.OPEN, evidence_note=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def test_task_to_read_marks_overdue():
    t = _task(due_date=date(2026, 6, 1), status=DecisionTaskStatus.OPEN)
    read = task_to_read(t, today=TODAY)
    assert read.is_overdue is True
    assert read.status is DecisionTaskStatus.OPEN  # stored status unchanged


def test_task_to_read_done_not_overdue():
    t = _task(due_date=date(2026, 6, 1), status=DecisionTaskStatus.DONE)
    assert task_to_read(t, today=TODAY).is_overdue is False


def test_build_protocol_groups_tasks_under_decisions():
    meeting = SimpleNamespace(
        id="m1", committee_id="c1",
        scheduled_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        location=None, status=MeetingStatus.HELD,
        created_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
        updated_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    decision = SimpleNamespace(
        id="d1", meeting_id="m1", agenda_item_id=None,
        text="Закупить СИЗ", decided_at=datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    tasks = [_task(id="t1", decision_id="d1", due_date=date(2026, 6, 1))]
    proto = build_protocol(meeting, [(decision, tasks)], today=TODAY)
    assert proto.meeting.id == "m1"
    assert len(proto.decisions) == 1
    assert proto.decisions[0].decision.text == "Закупить СИЗ"
    assert proto.decisions[0].tasks[0].is_overdue is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_committees_service.py -v`
Expected: FAIL — `ModuleNotFoundError: app.domains.committees.service`.

- [ ] **Step 3: Write the service**

Create `backend/app/domains/committees/service.py`:

```python
"""Read-projection + mapping helpers for committees срез-1 (P10-01).

Kept DB-agnostic where possible: ``task_to_read`` / ``build_protocol`` take
already-loaded ORM rows (or SimpleNamespace in tests) so the overdue
projection and protocol grouping are unit-testable without a session.
"""
from __future__ import annotations

from datetime import date

from app.domains.committees.lifecycle import is_task_overdue
from app.schemas.committees import (
    DecisionRead,
    DecisionTaskRead,
    MeetingRead,
    ProtocolDecision,
    ProtocolRead,
)


def _today() -> date:
    return date.today()


def task_to_read(task, *, today: date | None = None) -> DecisionTaskRead:
    today = today or _today()
    return DecisionTaskRead(
        id=task.id,
        decision_id=task.decision_id,
        assignee_person_id=task.assignee_person_id,
        due_date=task.due_date,
        status=task.status,
        evidence_note=task.evidence_note,
        is_overdue=is_task_overdue(task.status, task.due_date, today),
    )


def build_protocol(meeting, decisions_with_tasks, *, today: date | None = None) -> ProtocolRead:
    """decisions_with_tasks: iterable of ``(decision_row, [task_rows])``."""
    today = today or _today()
    grouped = [
        ProtocolDecision(
            decision=DecisionRead.model_validate(decision, from_attributes=True),
            tasks=[task_to_read(t, today=today) for t in tasks],
        )
        for decision, tasks in decisions_with_tasks
    ]
    return ProtocolRead(
        meeting=MeetingRead.model_validate(meeting, from_attributes=True),
        decisions=grouped,
    )
```

Add to `backend/app/domains/committees/__init__.py` exports:

```python
from app.domains.committees.service import build_protocol, task_to_read
```

(append `"build_protocol"`, `"task_to_read"` to `__all__`).

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_committees_service.py -v`
Expected: PASS (3 tests).

> Note: if `DecisionRead.model_validate(..., from_attributes=True)` rejects the kwarg, set `model_config = ConfigDict(from_attributes=True)` on `BaseSchema` consumers instead — check `app/schemas/base.py` for the existing convention and match it (most repo Read schemas already enable `from_attributes`). Adjust the two `model_validate` calls to plain `model_validate(obj)` if base already enables it.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/committees/service.py backend/app/domains/committees/__init__.py backend/tests/test_committees_service.py
git commit -m "feat(committees): service projection helpers (overdue + protocol)"
```

---

## Task 6: HTTP routes + router registration

**Files:**
- Create: `backend/app/api/routes/committees.py`
- Modify: `backend/app/api/v1/route_groups.py`
- Test: `backend/tests/test_committees_api.py`

This task mirrors `backend/app/api/routes/ppe.py` exactly: `SessionDep`/`TenantDep`, `abac` access deps, `compute_list_etag` + `apply_etag_response_headers` + 304 branch on lists, tenant-scoped queries with 404 helpers, `MeetingTransitionError` → 409. API tests mock the session at the route boundary (repo convention — no live DB).

- [ ] **Step 1: Write the failing API test (transition + overdue projection, mocked session)**

Create `backend/tests/test_committees_api.py`:

```python
"""API-contract tests for committees routes (P10-01), mocking session.

Follows the repo convention (see test_work_permit_electrical_groups_api.py):
patch the route module's session/query helpers with AsyncMock — no live DB.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import committees as routes
from app.domains.committees.lifecycle import MeetingTransitionError
from app.models.committees import MeetingStatus, DecisionTaskStatus
from app.schemas.committees import MeetingStatusUpdate, DecisionCreate


def _tenant():
    return SimpleNamespace(id="tenant-1")


def _meeting(status=MeetingStatus.PLANNED):
    now = datetime(2026, 6, 25, tzinfo=timezone.utc)
    return SimpleNamespace(
        id="m1", committee_id="c1", tenant_id="tenant-1",
        scheduled_at=now, location=None, status=status,
        created_at=now, updated_at=now, deleted_at=None,
    )


@pytest.mark.asyncio
async def test_transition_meeting_rejects_illegal(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.HELD)))
    with pytest.raises(Exception) as exc:
        await routes.update_meeting(
            mid="m1",
            payload=MeetingStatusUpdate(status=MeetingStatus.PLANNED),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    # route maps MeetingTransitionError -> HTTPException 409
    assert getattr(exc.value, "status_code", None) == 409


@pytest.mark.asyncio
async def test_add_decision_requires_held(monkeypatch):
    session = AsyncMock()
    monkeypatch.setattr(routes, "_get_meeting", AsyncMock(return_value=_meeting(MeetingStatus.PLANNED)))
    with pytest.raises(Exception) as exc:
        await routes.create_decision(
            mid="m1",
            payload=DecisionCreate(text="x"),
            tenant=_tenant(),
            session=session,
            access=SimpleNamespace(),
        )
    assert getattr(exc.value, "status_code", None) == 409
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_committees_api.py -v`
Expected: FAIL — `ModuleNotFoundError: app.api.routes.committees`.

- [ ] **Step 3: Write the routes module**

Create `backend/app/api/routes/committees.py`. (Full module — mirrors ppe.py wiring.)

```python
"""Endpoints for committees / commissions / meetings (P10-01 срез-1, TZ B.17)."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.domains.committees.lifecycle import (
    MeetingTransitionError,
    ensure_meeting_held,
    validate_meeting_transition,
)
from app.domains.committees.service import build_protocol, task_to_read
from app.models.committees import (
    Committee,
    CommitteeAgendaItem,
    CommitteeDecision,
    CommitteeDecisionTask,
    CommitteeMeeting,
    CommitteeMember,
)
from app.models.tenanting import Tenant
from app.schemas.committees import (
    AgendaItemCreate,
    AgendaItemRead,
    CommitteeCreate,
    CommitteePage,
    CommitteeRead,
    CommitteeUpdate,
    DecisionCreate,
    DecisionRead,
    DecisionTaskCreate,
    DecisionTaskRead,
    DecisionTaskUpdate,
    MeetingCreate,
    MeetingPage,
    MeetingRead,
    MeetingStatusUpdate,
    MemberCreate,
    MemberRead,
    ProtocolRead,
)

router = APIRouter(prefix="/committees", tags=["committees"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


_ROLES = ["admin"]
Access = Annotated[AccessContext, Depends(abac(_tenant_resource_id, required_roles=_ROLES))]


def _conflict(exc: MeetingTransitionError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="COMMITTEE_TRANSITION_INVALID", message=str(exc), error_type="committees"
        ),
    )


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"{what} not found")


# --- tenant-scoped getters (patched in tests) ---
async def _get_committee(session: AsyncSession, tenant: Tenant, cid: str) -> Committee:
    row = (
        await session.execute(
            select(Committee).where(
                Committee.id == cid,
                Committee.tenant_id == tenant.id,
                Committee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Committee")
    return row


async def _get_meeting(session: AsyncSession, tenant: Tenant, mid: str) -> CommitteeMeeting:
    row = (
        await session.execute(
            select(CommitteeMeeting).where(
                CommitteeMeeting.id == mid,
                CommitteeMeeting.tenant_id == tenant.id,
                CommitteeMeeting.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Meeting")
    return row


async def _get_decision(session: AsyncSession, tenant: Tenant, did: str) -> CommitteeDecision:
    row = (
        await session.execute(
            select(CommitteeDecision).where(
                CommitteeDecision.id == did, CommitteeDecision.tenant_id == tenant.id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Decision")
    return row


async def _get_task(session: AsyncSession, tenant: Tenant, tid: str) -> CommitteeDecisionTask:
    row = (
        await session.execute(
            select(CommitteeDecisionTask).where(
                CommitteeDecisionTask.id == tid,
                CommitteeDecisionTask.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Task")
    return row


# --- Committees ---
@router.get("", response_model=CommitteePage)
async def list_committees(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> CommitteePage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    stmt = (
        select(Committee)
        .where(Committee.tenant_id == tenant.id, Committee.deleted_at.is_(None))
        .order_by(Committee.name.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).where(
                Committee.tenant_id == tenant.id, Committee.deleted_at.is_(None)
            )
        )
    ).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", int(total or 0)), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return CommitteePage(
        items=[CommitteeRead.model_validate(c, from_attributes=True) for c in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=CommitteeRead, status_code=status.HTTP_201_CREATED)
async def create_committee(
    payload: CommitteeCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> CommitteeRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    row = Committee(
        tenant_id=tenant.id,
        kind=payload.kind,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(row)
    await session.flush()
    return CommitteeRead.model_validate(row, from_attributes=True)


@router.get("/{cid}", response_model=CommitteeRead)
async def get_committee(cid: str, tenant: TenantDep, session: SessionDep, access: Access) -> CommitteeRead:
    row = await _get_committee(session, tenant, cid)
    return CommitteeRead.model_validate(row, from_attributes=True)


@router.patch("/{cid}", response_model=CommitteeRead)
async def update_committee(
    cid: str, payload: CommitteeUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> CommitteeRead:
    row = await _get_committee(session, tenant, cid)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    return CommitteeRead.model_validate(row, from_attributes=True)


# --- Members ---
@router.post("/{cid}/members", response_model=MemberRead, status_code=status.HTTP_201_CREATED)
async def add_member(
    cid: str, payload: MemberCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> MemberRead:
    await _get_committee(session, tenant, cid)
    row = CommitteeMember(
        tenant_id=tenant.id, committee_id=cid, person_id=payload.person_id, role=payload.role
    )
    session.add(row)
    await session.flush()
    return MemberRead.model_validate(row, from_attributes=True)


@router.delete("/{cid}/members/{mid}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    cid: str, mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> Response:
    row = (
        await session.execute(
            select(CommitteeMember).where(
                CommitteeMember.id == mid,
                CommitteeMember.committee_id == cid,
                CommitteeMember.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise _not_found("Member")
    await session.delete(row)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --- Meetings ---
@router.get("/{cid}/meetings", response_model=MeetingPage)
async def list_meetings(
    cid: str,
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: Access,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> MeetingPage | Response:
    await _get_committee(session, tenant, cid)
    stmt = (
        select(CommitteeMeeting)
        .where(
            CommitteeMeeting.committee_id == cid,
            CommitteeMeeting.tenant_id == tenant.id,
            CommitteeMeeting.deleted_at.is_(None),
        )
        .order_by(CommitteeMeeting.scheduled_at.desc())
        .limit(limit)
        .offset(offset)
    )
    items = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(
            select(func.count()).where(
                CommitteeMeeting.committee_id == cid,
                CommitteeMeeting.tenant_id == tenant.id,
                CommitteeMeeting.deleted_at.is_(None),
            )
        )
    ).scalar_one()
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("cid", cid), ("total", int(total or 0)), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return MeetingPage(
        items=[MeetingRead.model_validate(m, from_attributes=True) for m in items],
        total=int(total or 0),
        limit=limit,
        offset=offset,
    )


@router.post("/{cid}/meetings", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def schedule_meeting(
    cid: str, payload: MeetingCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> MeetingRead:
    await _get_committee(session, tenant, cid)
    row = CommitteeMeeting(
        tenant_id=tenant.id, committee_id=cid,
        scheduled_at=payload.scheduled_at, location=payload.location,
    )
    session.add(row)
    await session.flush()
    return MeetingRead.model_validate(row, from_attributes=True)


@router.get("/meetings/{mid}", response_model=MeetingRead)
async def get_meeting(mid: str, tenant: TenantDep, session: SessionDep, access: Access) -> MeetingRead:
    row = await _get_meeting(session, tenant, mid)
    return MeetingRead.model_validate(row, from_attributes=True)


@router.patch("/meetings/{mid}", response_model=MeetingRead)
async def update_meeting(
    mid: str, payload: MeetingStatusUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> MeetingRead:
    row = await _get_meeting(session, tenant, mid)
    try:
        validate_meeting_transition(row.status, payload.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    row.status = payload.status
    await session.flush()
    return MeetingRead.model_validate(row, from_attributes=True)


@router.post("/meetings/{mid}/agenda-items", response_model=AgendaItemRead, status_code=status.HTTP_201_CREATED)
async def create_agenda_item(
    mid: str, payload: AgendaItemCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> AgendaItemRead:
    await _get_meeting(session, tenant, mid)
    row = CommitteeAgendaItem(
        tenant_id=tenant.id, meeting_id=mid,
        seq=payload.seq, title=payload.title, presenter_person_id=payload.presenter_person_id,
    )
    session.add(row)
    await session.flush()
    return AgendaItemRead.model_validate(row, from_attributes=True)


# --- Decisions ---
@router.post("/meetings/{mid}/decisions", response_model=DecisionRead, status_code=status.HTTP_201_CREATED)
async def create_decision(
    mid: str, payload: DecisionCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionRead:
    meeting = await _get_meeting(session, tenant, mid)
    try:
        ensure_meeting_held(meeting.status)
    except MeetingTransitionError as exc:
        raise _conflict(exc)
    row = CommitteeDecision(
        tenant_id=tenant.id, meeting_id=mid,
        agenda_item_id=payload.agenda_item_id, text=payload.text,
    )
    session.add(row)
    await session.flush()
    return DecisionRead.model_validate(row, from_attributes=True)


@router.get("/meetings/{mid}/protocol", response_model=ProtocolRead)
async def get_protocol(
    mid: str, tenant: TenantDep, session: SessionDep, access: Access
) -> ProtocolRead:
    meeting = await _get_meeting(session, tenant, mid)
    decisions = list(
        (
            await session.execute(
                select(CommitteeDecision)
                .where(
                    CommitteeDecision.meeting_id == mid,
                    CommitteeDecision.tenant_id == tenant.id,
                )
                .order_by(CommitteeDecision.decided_at.asc())
            )
        ).scalars().all()
    )
    pairs = []
    for d in decisions:
        tasks = list(
            (
                await session.execute(
                    select(CommitteeDecisionTask).where(
                        CommitteeDecisionTask.decision_id == d.id,
                        CommitteeDecisionTask.tenant_id == tenant.id,
                    )
                )
            ).scalars().all()
        )
        pairs.append((d, tasks))
    return build_protocol(meeting, pairs)


@router.post("/decisions/{did}/tasks", response_model=DecisionTaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    did: str, payload: DecisionTaskCreate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionTaskRead:
    await _get_decision(session, tenant, did)
    row = CommitteeDecisionTask(
        tenant_id=tenant.id, decision_id=did,
        assignee_person_id=payload.assignee_person_id,
        due_date=payload.due_date, evidence_note=payload.evidence_note,
    )
    session.add(row)
    await session.flush()
    return task_to_read(row)


@router.patch("/tasks/{tid}", response_model=DecisionTaskRead)
async def update_task(
    tid: str, payload: DecisionTaskUpdate, tenant: TenantDep, session: SessionDep, access: Access
) -> DecisionTaskRead:
    row = await _get_task(session, tenant, tid)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    await session.flush()
    return task_to_read(row)
```

- [ ] **Step 4: Register the router**

Modify `backend/app/api/v1/route_groups.py`:
1. Add `committees,` to the alphabetical import block (the `from app.api.routes import (...)` list — insert near `calendar`/`contracts`).
2. Add the registration tuple inside `COMPLIANCE_AND_ADMIN_ROUTER_REGISTRATIONS`, next to the other domain routers:

```python
    (committees.router, {"tags": ["committees"]}),
```

- [ ] **Step 5: Run the API tests to verify they pass**

Run: `python -m pytest backend/tests/test_committees_api.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Verify the app imports & router is mounted (no wiring regressions)**

Run: `python -c "from app.api.v1.route_groups import create_tenant_router; r=create_tenant_router(); paths=[x.path for x in r.routes]; assert any('/committees' in p for p in paths), paths; print('committees mounted:', sum('/committees' in p for p in paths), 'routes')"`
Expected: prints a non-zero route count. (If import requires app settings/env, run instead: `python -m pytest backend/tests/test_committees_api.py backend/tests/test_orm_mapper_configuration.py -v`.)

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/routes/committees.py backend/app/api/v1/route_groups.py backend/tests/test_committees_api.py
git commit -m "feat(committees): срез-1 HTTP routes + router registration"
```

---

## Task 7: Feature flag + tenant-isolation tests

**Files:**
- Modify: `backend/app/api/routes/committees.py` (flag guard)
- Test: `backend/tests/test_committees_flag_and_isolation.py`

- [ ] **Step 1: Write the failing flag + isolation test**

Create `backend/tests/test_committees_flag_and_isolation.py`:

```python
"""Flag gate (default off) + cross-tenant 404 isolation (P10-01).

The flag helper is tested directly (not through an endpoint) so the assertion
is about the flag decision, not about TenantContextValidator/DI side effects.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.routes import committees as routes


def _tenant(tid="tenant-1"):
    return SimpleNamespace(id=tid)


@pytest.mark.asyncio
async def test_require_enabled_raises_when_flag_off(monkeypatch):
    # is_feature_enabled returns False (default-off) -> guard raises 404
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=False))
    with pytest.raises(Exception) as exc:
        await routes._require_committees_enabled(AsyncMock(), _tenant())
    assert getattr(exc.value, "status_code", None) == 404


@pytest.mark.asyncio
async def test_require_enabled_passes_when_flag_on(monkeypatch):
    monkeypatch.setattr(routes, "is_feature_enabled", AsyncMock(return_value=True))
    # no exception
    await routes._require_committees_enabled(AsyncMock(), _tenant())


@pytest.mark.asyncio
async def test_require_enabled_passes_default_false_arg(monkeypatch):
    # assert the guard requests default=False (a missing flag must NOT default-on)
    spy = AsyncMock(return_value=False)
    monkeypatch.setattr(routes, "is_feature_enabled", spy)
    with pytest.raises(Exception):
        await routes._require_committees_enabled(AsyncMock(), _tenant())
    assert spy.await_args.kwargs.get("default") is False


@pytest.mark.asyncio
async def test_get_committee_cross_tenant_is_404():
    # _get_committee filters by tenant_id; a foreign row resolves to None -> 404
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=SimpleNamespace(scalar_one_or_none=lambda: None)
    )
    with pytest.raises(Exception) as exc:
        await routes._get_committee(session, _tenant("tenant-1"), "committee-owned-by-tenant-2")
    assert getattr(exc.value, "status_code", None) == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_committees_flag_and_isolation.py -v`
Expected: FAIL — `_require_committees_enabled` / `_feature_off` not defined.

- [ ] **Step 3: Add the flag guard to the routes module**

In `backend/app/api/routes/committees.py`, add the flag import to the existing import block (top of file, alongside the other `app.core` imports):

```python
from app.core.feature_flags import is_feature_enabled
```

Then add the helpers near the top (after `router = ...`):

```python
_FEATURE_CODE = "committees"


def _feature_off() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=api_problem_detail(
            code="COMMITTEES_DISABLED",
            message="Committees module is not enabled for this tenant",
            error_type="committees",
        ),
    )


async def _require_committees_enabled(session: AsyncSession, tenant: Tenant) -> None:
    enabled = await is_feature_enabled(session, str(tenant.id), _FEATURE_CODE, default=False)
    if not enabled:
        raise _feature_off()
```

Then call `await _require_committees_enabled(session, tenant)` as the first line (after `TenantContextValidator.ensure_tenant_context(tenant)`) in **every** endpoint (`list_committees`, `create_committee`, `get_committee`, `update_committee`, `add_member`, `remove_member`, `list_meetings`, `schedule_meeting`, `get_meeting`, `update_meeting`, `create_agenda_item`, `create_decision`, `get_protocol`, `create_task`, `update_task`).

> Pattern note: the getters `_get_committee`/`_get_meeting`/etc. are reached only after the flag check in their callers, so adding the guard to each public endpoint is sufficient. Keep the call ordering identical across endpoints for reviewability.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_committees_flag_and_isolation.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the whole committees suite**

Run: `python -m pytest backend/tests/test_committees_*.py backend/tests/test_cmt01_committees_migration.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/committees.py backend/tests/test_committees_flag_and_isolation.py
git commit -m "feat(committees): default-off feature flag + cross-tenant isolation tests"
```

---

## Task 8: Frontend (thin list/detail UI)

**Files:**
- Create: `frontend/src/api/committees.ts`
- Create: `frontend/src/pages/committees/CommitteesPage.tsx`
- Modify: route registration + nav (match existing pattern — see note)

> Before coding: read `frontend/src/pages/warehouse/WarehousePage.tsx` and an existing `frontend/src/api/*.ts` client to copy the fetch/error/empty/loading conventions and the auth/tenant header wiring. Read how a page is registered in the router (`frontend/src/App.tsx` or `frontend/src/router*.tsx`) and how nav items are gated by feature flag.

- [ ] **Step 1: Write the API client**

Create `frontend/src/api/committees.ts` mirroring an existing client's base (`apiFetch`/axios instance — match the repo). Minimum surface:

```ts
import { api } from "./client"; // match the actual shared client import in the repo

export interface Committee {
  id: string;
  kind: string;
  name: string;
  description: string | null;
  is_active: boolean;
}

export interface Meeting {
  id: string;
  committee_id: string;
  scheduled_at: string;
  location: string | null;
  status: "planned" | "held" | "cancelled";
}

export interface DecisionTask {
  id: string;
  decision_id: string;
  assignee_person_id: string | null;
  due_date: string | null;
  status: "open" | "in_progress" | "done" | "overdue";
  evidence_note: string | null;
  is_overdue: boolean;
}

export const committeesApi = {
  list: () => api.get<{ items: Committee[]; total: number }>("/committees"),
  get: (id: string) => api.get<Committee>(`/committees/${id}`),
  meetings: (cid: string) =>
    api.get<{ items: Meeting[]; total: number }>(`/committees/${cid}/meetings`),
  protocol: (mid: string) => api.get(`/committees/meetings/${mid}/protocol`),
};
```

(Adjust `api`/`api.get` to the repo's actual client signature discovered in the pre-step.)

- [ ] **Step 2: Write the page**

Create `frontend/src/pages/committees/CommitteesPage.tsx` — a list of committees → on select, show meetings; on meeting select, show the protocol (decisions + tasks with an "просрочено" badge when `is_overdue`). Reuse the repo's list/empty/error/retry components (copy the structure from `WarehousePage.tsx`). Gate the nav entry behind the `committees` flag using the existing feature-flag hook.

- [ ] **Step 3: Register route + nav**

Add the page to the router and a nav item (flag-gated) following the exact pattern found in the pre-step.

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npm run typecheck` (or the repo's script — check `frontend/package.json`).
Expected: no type errors in the new files.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/committees.ts frontend/src/pages/committees/ frontend/src/App.tsx
git commit -m "feat(committees): thin list/detail frontend (flag-gated)"
```

---

## Task 9: Docs, seed, matrix update

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `docs/audit/TZ_COVERAGE_MATRIX.md` and the roadmap reconciliation row (`docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`)
- Create/modify: seed data (locate the existing seed/demo loader first)

- [ ] **Step 1: Add CHANGELOG entry**

Append under the unreleased section:

```markdown
### Added
- Committees / commissions / meetings module (P10-01 срез-1, TZ B.17): committee→meeting→agenda→decision→decision-task with CRUD API, lifecycle guards (meeting planned→held→cancelled; decisions only on held), read-time overdue flag, ETag list caching, tenant isolation, behind default-off `committees` feature flag. Voting, invitations, execution KPI dashboard, meetings journal deferred to срез-2.
```

- [ ] **Step 2: Add seed data**

Locate the seed/demo loader (`git grep -l "def seed\|demo_tenant\|seed_" backend/app | head`). Add one committee (kind `osms`) + one `held` meeting + one agenda item + one decision + one task with a past `due_date` (to demonstrate the overdue badge). Match the loader's existing insertion style.

- [ ] **Step 3: Update the coverage matrix + roadmap reconciliation**

In `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` Section B reconciliation table, change the `P10-01` row from `❌ not started` to `🟡 partial` with evidence: `domains/committees/`, `models/committees.py`, migration `cmt01`, routes `api/routes/committees.py`. List the срез-2 deferrals (voting, invitations, KPI dashboard, journal, Command Center projection). Update the summary line counts (3 partial-or-merged committee row added; "not started" 6→5).

If `docs/audit/TZ_COVERAGE_MATRIX.md` has a B.17 row, set it to `partial` with the same evidence; otherwise add one.

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md docs/audit/TZ_COVERAGE_MATRIX.md docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md backend/app/<seed_file>
git commit -m "docs(committees): CHANGELOG + matrix P10-01 -> partial + seed data"
```

---

## Final verification

- [ ] **Run the full committees suite + guards**

Run:
```
python -m pytest backend/tests/test_committees_models.py backend/tests/test_cmt01_committees_migration.py backend/tests/test_committees_lifecycle.py backend/tests/test_committees_schemas.py backend/tests/test_committees_service.py backend/tests/test_committees_api.py backend/tests/test_committees_flag_and_isolation.py backend/tests/test_orm_mapper_configuration.py -v
```
Expected: all PASS. Note the Python version used; if not 3.12.x, state the mismatch (CI on Py3.12.12 is source of truth per CLAUDE.md).

- [ ] **Confirm no unrelated files changed**

Run: `git status` and `git diff --stat main`. Expected: only committees-module files + the 3 docs files.

---

## Acceptance checklist (срез-1)

- [ ] `committee → meeting → agenda → decision → task` works end-to-end via API.
- [ ] ETag/304 on `GET /committees` and `GET /committees/{id}/meetings`.
- [ ] Meeting transitions guarded (illegal → 409); decisions only on `held` (→ 409).
- [ ] `is_overdue` computed at read; stored status never silently mutated.
- [ ] `committees` flag default-off isolates the module; cross-tenant reads → 404.
- [ ] Thin UI lists committees → meetings → protocol with overdue badge.
- [ ] `P10-01` → `partial` in matrix/roadmap with срез-2 deferrals listed.
- [ ] All new tests green (record Py version).

## Deferred to срез-2 (recorded, not dropped)
Voting/quorum · invitations/notifications · execution-KPI dashboard · meetings journal + protocol numbering · projection of decision-tasks into Command Center (W2).
```
