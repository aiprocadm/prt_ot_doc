# Prescriptions Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give prescription `status` an enforced state machine (linear + rework loop) with resolution evidence and an inspector-verification step, exposed via a single transition endpoint.

**Architecture:** A pure FSM module (`app/domains/prescriptions/lifecycle.py`, no DB imports) defines allowed transitions; a new `POST /prescriptions/{id}/transition` endpoint validates against it, enforces evidence-on-complete and admin/owner-only verification, and stamps `closed_at` on terminal states. `PATCH`/create lose `status` (status moves only through `/transition`). An additive migration adds `evidence` + `closed_at` columns and extends the `prescriptionstatus` PG enum with `verified`.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async), Alembic, Pydantic v2, pytest. Spec: `docs/superpowers/specs/2026-05-30-prescriptions-lifecycle-design.md`.

**Branch:** `feat/wa-prescriptions-lifecycle` (already created, stacked on `fix/featureenablement-cross-base-fk`).

**Local test runner:** `.venv\Scripts\python.exe` (Py3.13/Win). App-free tests live under `backend/tests/` (no `create_app` conftest → safe locally). The app-booting API test (Task 5) runs locally but is slow; CI on 3.12.12 is canonical (`[[local_env_drift_windows]]`).

---

### Task 1: Model — `verified` enum value + `evidence`/`closed_at` columns

**Files:**
- Modify: `backend/app/models/models.py` (`PrescriptionStatus` ~line 2540; `Prescription` ~line 2547-2565)
- Test: `backend/tests/test_prescription_lifecycle_model.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_prescription_lifecycle_model.py
"""Pin: prescription lifecycle model fields (TZ-3.4-V12-01)."""
from __future__ import annotations


def test_prescription_status_has_verified() -> None:
    from app.models.models import PrescriptionStatus

    assert PrescriptionStatus.VERIFIED.value == "verified"


def test_prescription_has_lifecycle_columns() -> None:
    from app.models.models import Prescription

    cols = Prescription.__table__.c
    assert "evidence" in cols
    assert "closed_at" in cols
    assert cols["evidence"].nullable is True
    assert cols["closed_at"].nullable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescription_lifecycle_model.py -p no:cacheprovider -q`
Expected: FAIL — `AttributeError: VERIFIED` (enum lacks the value) and/or missing columns.

- [ ] **Step 3: Add the enum value**

In `backend/app/models/models.py`, `class PrescriptionStatus` — add `VERIFIED` between `COMPLETED` and `CANCELLED`:

```python
class PrescriptionStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    VERIFIED = "verified"
    CANCELLED = "cancelled"
```

- [ ] **Step 4: Add the two columns**

In `class Prescription`, after the `assignee_id` column and before the `inspection`/`incident`/`assignee` relationships, add:

```python
    evidence: Mapped[str | None] = mapped_column(Text)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

Verify `Text`, `DateTime`, and `datetime` are already imported at the top of `models.py` (they are used by other models in this file). If any is missing, add it to the existing `from sqlalchemy import ...` / `from datetime import ...` lines.

- [ ] **Step 5: Run test to verify it passes**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescription_lifecycle_model.py -p no:cacheprovider -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/models.py backend/tests/test_prescription_lifecycle_model.py
git commit -m "feat(prescriptions): add verified status + evidence/closed_at columns (TZ-3.4-V12-01)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: FSM domain module — `app/domains/prescriptions/lifecycle.py`

**Files:**
- Create: `backend/app/domains/prescriptions/__init__.py`
- Create: `backend/app/domains/prescriptions/lifecycle.py`
- Test: `backend/tests/test_prescription_lifecycle.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_prescription_lifecycle.py
"""Unit tests for the prescription status FSM (TZ-3.4-V12-01). App-free."""
from __future__ import annotations

import pytest

from app.domains.prescriptions.lifecycle import (
    InvalidTransition,
    TERMINAL_STATES,
    VERIFY_ROLES,
    is_terminal,
    requires_evidence,
    validate_transition,
)
from app.models.models import PrescriptionStatus as S


@pytest.mark.parametrize(
    "current,target",
    [
        (S.OPEN, S.IN_PROGRESS),
        (S.OPEN, S.CANCELLED),
        (S.IN_PROGRESS, S.COMPLETED),
        (S.IN_PROGRESS, S.CANCELLED),
        (S.COMPLETED, S.VERIFIED),
        (S.COMPLETED, S.IN_PROGRESS),
    ],
)
def test_allowed_transitions(current, target) -> None:
    validate_transition(current, target)  # must not raise


@pytest.mark.parametrize(
    "current,target",
    [
        (S.OPEN, S.COMPLETED),
        (S.OPEN, S.VERIFIED),
        (S.IN_PROGRESS, S.VERIFIED),
        (S.COMPLETED, S.CANCELLED),
        (S.CANCELLED, S.OPEN),
        (S.VERIFIED, S.IN_PROGRESS),
    ],
)
def test_invalid_transitions_raise(current, target) -> None:
    with pytest.raises(InvalidTransition):
        validate_transition(current, target)


@pytest.mark.parametrize("state", [S.VERIFIED, S.CANCELLED])
def test_terminal_states_reject_all_other_targets(state) -> None:
    for target in S:
        if target == state:
            continue
        with pytest.raises(InvalidTransition):
            validate_transition(state, target)


@pytest.mark.parametrize("state", list(S))
def test_self_transition_is_noop(state) -> None:
    validate_transition(state, state)  # must not raise


def test_terminal_states_constant() -> None:
    assert TERMINAL_STATES == frozenset({S.VERIFIED, S.CANCELLED})


def test_is_terminal() -> None:
    assert is_terminal(S.VERIFIED)
    assert is_terminal(S.CANCELLED)
    assert not is_terminal(S.OPEN)


def test_requires_evidence_only_for_completed() -> None:
    assert requires_evidence(S.COMPLETED)
    for s in (S.OPEN, S.IN_PROGRESS, S.VERIFIED, S.CANCELLED):
        assert not requires_evidence(s)


def test_verify_roles_constant() -> None:
    assert VERIFY_ROLES == frozenset({"admin", "owner"})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescription_lifecycle.py -p no:cacheprovider -q`
Expected: FAIL — `ModuleNotFoundError: app.domains.prescriptions.lifecycle`.

- [ ] **Step 3: Create the package marker**

```python
# backend/app/domains/prescriptions/__init__.py
"""Prescriptions domain (status lifecycle)."""
```

- [ ] **Step 4: Implement the FSM module**

```python
# backend/app/domains/prescriptions/lifecycle.py
"""Prescription status lifecycle — pure FSM (no DB / no app imports).

TZ-3.4-V12-01. Linear + rework loop:
OPEN -> IN_PROGRESS -> COMPLETED -> VERIFIED (terminal); COMPLETED -> IN_PROGRESS
on a failed re-inspection; CANCELLED reachable only from OPEN/IN_PROGRESS;
VERIFIED/CANCELLED terminal. A self-transition is an idempotent no-op.
"""
from __future__ import annotations

from app.models.models import PrescriptionStatus

_S = PrescriptionStatus

ALLOWED_TRANSITIONS: dict[PrescriptionStatus, frozenset[PrescriptionStatus]] = {
    _S.OPEN: frozenset({_S.IN_PROGRESS, _S.CANCELLED}),
    _S.IN_PROGRESS: frozenset({_S.COMPLETED, _S.CANCELLED}),
    _S.COMPLETED: frozenset({_S.VERIFIED, _S.IN_PROGRESS}),
    _S.VERIFIED: frozenset(),
    _S.CANCELLED: frozenset(),
}

TERMINAL_STATES: frozenset[PrescriptionStatus] = frozenset({_S.VERIFIED, _S.CANCELLED})

# Segregation of duties: only these roles may move a prescription to VERIFIED.
VERIFY_ROLES: frozenset[str] = frozenset({"admin", "owner"})


class InvalidTransition(Exception):
    """Raised when a status transition is not permitted by the FSM."""

    def __init__(self, current: PrescriptionStatus, target: PrescriptionStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Cannot transition prescription from {current.value} to {target.value}"
        )


def validate_transition(current: PrescriptionStatus, target: PrescriptionStatus) -> None:
    """Raise :class:`InvalidTransition` unless ``target`` is reachable from
    ``current``. A self-transition (``current == target``) is always allowed."""
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(current, target)


def is_terminal(status: PrescriptionStatus) -> bool:
    return status in TERMINAL_STATES


def requires_evidence(target: PrescriptionStatus) -> bool:
    return target == PrescriptionStatus.COMPLETED
```

- [ ] **Step 5: Run test to verify it passes**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescription_lifecycle.py -p no:cacheprovider -q`
Expected: PASS (all parametrized cases green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/domains/prescriptions/ backend/tests/test_prescription_lifecycle.py
git commit -m "feat(prescriptions): pure status FSM module + unit tests (TZ-3.4-V12-01)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Additive migration `wa03` — columns + enum extension

**Files:**
- Create: `backend/app/migrations/versions/20260530_wa03_prescription_lifecycle.py`
- Test: `backend/tests/test_wa03_prescription_lifecycle_migration.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_wa03_prescription_lifecycle_migration.py
"""Pin: wa03 prescription lifecycle migration (TZ-3.4-V12-01). App-free."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260530_wa03_prescription_lifecycle.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wa03_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_revision_metadata() -> None:
    mod = _load()
    assert mod.revision == "20260530_wa03_prescription_lifecycle"
    assert mod.down_revision == "20260530_wa02_featureenablement_drop_feature_fk"
    assert mod.depends_on is None


def test_upgrade_downgrade_shape() -> None:
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)

    src = _MIGRATION.read_text(encoding="utf-8")
    # additive columns on inspection_prescription
    assert 'add_column("inspection_prescription"' in src
    assert '"evidence"' in src
    assert '"closed_at"' in src
    # enum extension, postgres-guarded, idempotent
    assert "ALTER TYPE prescriptionstatus ADD VALUE IF NOT EXISTS 'verified'" in src
    assert 'dialect.name == "postgresql"' in src
    # downgrade drops both columns
    assert 'drop_column("inspection_prescription", "closed_at")' in src
    assert 'drop_column("inspection_prescription", "evidence")' in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_wa03_prescription_lifecycle_migration.py -p no:cacheprovider -q`
Expected: FAIL — migration file does not exist (load raises `FileNotFoundError`).

- [ ] **Step 3: Write the migration**

```python
# backend/app/migrations/versions/20260530_wa03_prescription_lifecycle.py
"""prescription lifecycle: evidence + closed_at cols + verified enum value

TZ-3.4-V12-01 / W-A item #2. Additive. Adds two nullable columns to
inspection_prescription and extends the prescriptionstatus PG enum with
'verified'. No data backfill.

The new enum value is NOT used (no UPDATE/cast) in this migration, so the
single ALTER TYPE ADD VALUE is transaction-safe on PG12+ — mirrors the
precedent in 20260328_next55_templates_lifecycle. SQLite has no enum type
(the column behaves as TEXT) and the test harness builds schema from ORM
metadata, so no SQLite DDL is needed here.

Chains off the W-A head 20260530_wa02_featureenablement_drop_feature_fk. The
repo runs ``alembic upgrade heads`` (plural — many heads by design); this
additive change applies regardless of the other parallel branches.

Revision ID: 20260530_wa03_prescription_lifecycle
Revises: 20260530_wa02_featureenablement_drop_feature_fk
Create Date: 2026-05-30 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_wa03_prescription_lifecycle"
down_revision = "20260530_wa02_featureenablement_drop_feature_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "inspection_prescription", sa.Column("evidence", sa.Text(), nullable=True)
    )
    op.add_column(
        "inspection_prescription",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TYPE prescriptionstatus ADD VALUE IF NOT EXISTS 'verified'"
        )


def downgrade() -> None:
    op.drop_column("inspection_prescription", "closed_at")
    op.drop_column("inspection_prescription", "evidence")
    # The 'verified' enum value is intentionally NOT removed: Postgres cannot
    # DROP a value from an enum type without recreating it (documented one-way,
    # matching repo precedent for in-place enum extensions).
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_wa03_prescription_lifecycle_migration.py -p no:cacheprovider -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Verify the alembic graph (head count unchanged at 8, wa03 is the new W-A head)**

Run: `& ".venv\Scripts\python.exe" -m alembic -c backend/alembic.ini heads 2>&1 | Select-String wa03`
Expected: `20260530_wa03_prescription_lifecycle (head)` appears; total head count is unchanged from before (wa03 replaces wa02 as the W-A-branch head). If `alembic` cannot connect to a DB it still prints the head graph offline. If the `-c` path differs, locate it with `Get-ChildItem -Recurse -Filter alembic.ini backend`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260530_wa03_prescription_lifecycle.py backend/tests/test_wa03_prescription_lifecycle_migration.py
git commit -m "feat(db): wa03 prescription lifecycle migration - evidence/closed_at + verified enum (TZ-3.4-V12-01)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Schemas — drop `status` from write models; add `evidence`/`closed_at`/transition

**Files:**
- Modify: `backend/app/schemas/prescriptions.py` (full rewrite — small file)
- Test: `backend/tests/test_prescription_schemas.py` (create)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_prescription_schemas.py
"""Prescription schema contract for the lifecycle (TZ-3.4-V12-01). App-free."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.models import PrescriptionStatus
from app.schemas.prescriptions import (
    PrescriptionCreate,
    PrescriptionRead,
    PrescriptionTransition,
    PrescriptionUpdate,
)


def test_create_has_no_status_field() -> None:
    assert "status" not in PrescriptionCreate.model_fields


def test_update_has_no_status_field() -> None:
    assert "status" not in PrescriptionUpdate.model_fields


def test_read_exposes_evidence_and_closed_at() -> None:
    fields = PrescriptionRead.model_fields
    assert "evidence" in fields
    assert "closed_at" in fields


def test_transition_defaults_and_target() -> None:
    t = PrescriptionTransition(to=PrescriptionStatus.IN_PROGRESS)
    assert t.to == PrescriptionStatus.IN_PROGRESS
    assert t.evidence is None
    assert t.note is None


def test_transition_requires_target() -> None:
    with pytest.raises(ValidationError):
        PrescriptionTransition()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescription_schemas.py -p no:cacheprovider -q`
Expected: FAIL — `ImportError: cannot import name 'PrescriptionTransition'` (and the status-field assertions fail).

- [ ] **Step 3: Rewrite the schema module**

```python
# backend/app/schemas/prescriptions.py
"""Schemas for inspection prescriptions."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.models import PrescriptionStatus
from app.schemas.base import BaseSchema


class PrescriptionCreate(BaseSchema):
    inspection_id: str = Field(min_length=1, max_length=36)
    incident_id: str | None = Field(default=None, min_length=1, max_length=36)
    description: str = Field(min_length=1)
    due_at: date | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)


class PrescriptionUpdate(BaseSchema):
    inspection_id: str | None = Field(default=None, min_length=1, max_length=36)
    incident_id: str | None = Field(default=None, min_length=1, max_length=36)
    description: str | None = Field(default=None, min_length=1)
    due_at: date | None = None
    assignee_id: str | None = Field(default=None, min_length=1, max_length=36)


class PrescriptionTransition(BaseSchema):
    """Body for POST /prescriptions/{id}/transition."""

    to: PrescriptionStatus
    evidence: str | None = Field(default=None, min_length=1)
    note: str | None = Field(default=None, min_length=1)


class PrescriptionRead(BaseSchema):
    id: str
    inspection_id: str
    incident_id: str | None
    description: str
    due_at: date | None
    status: PrescriptionStatus
    assignee_id: str | None
    evidence: str | None
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PrescriptionPage(BaseSchema):
    items: list[PrescriptionRead]
    total: int
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescription_schemas.py -p no:cacheprovider -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/prescriptions.py backend/tests/test_prescription_schemas.py
git commit -m "feat(prescriptions): status off write schemas; add transition + evidence/closed_at read (TZ-3.4-V12-01)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: API — transition endpoint, create forces OPEN, PATCH drops status

**Files:**
- Modify: `backend/app/api/routes/prescriptions.py` (imports; `create_prescription` ~line 188-196; add transition endpoint after `update_prescription` ~line 268)
- Test: `tests/api/test_prescriptions_lifecycle_api.py` (create)
- Modify: `tests/integration/test_prescriptions_api.py` (migrate the `OPEN→COMPLETED` PATCH)

- [ ] **Step 1: Write the failing API test**

```python
# tests/api/test_prescriptions_lifecycle_api.py
"""API contract for the prescription status lifecycle (TZ-3.4-V12-01):
FSM transitions, evidence-on-complete, admin/owner-only verification,
closed_at stamping, and PATCH no longer moving status.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import AuditLog, PrescriptionStatus, RoleEnum


async def _seed_company_site(sessionmaker, data_factory) -> tuple[str, str]:
    """Seed tenant + company + site via the data factory (there is no HTTP
    create-company endpoint — mirrors tests/integration/test_prescriptions_api.py);
    return (company_id, site_id)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, session=session
        )
        await session.commit()
        return company.id, site.id


async def _seed_prescription(async_client, headers, company_id: str, site_id: str) -> str:
    """Create inspection -> prescription over HTTP; return the prescription id."""
    insp_resp = await async_client.post(
        "/api/v1/inspections",
        json={
            "company_id": company_id,
            "site_id": site_id,
            "authority": "Ростехнадзор",
            "scheduled_at": date.today().isoformat(),
        },
        headers=headers,
    )
    assert insp_resp.status_code == status.HTTP_201_CREATED, insp_resp.text
    pres_resp = await async_client.post(
        "/api/v1/prescriptions",
        json={"inspection_id": insp_resp.json()["id"], "description": "Fix guardrail"},
        headers=headers,
    )
    assert pres_resp.status_code == status.HTTP_201_CREATED, pres_resp.text
    body = pres_resp.json()
    assert body["status"] == PrescriptionStatus.OPEN.value  # create forces OPEN
    return body["id"]


async def _transition(async_client, pid, headers, to, **extra):
    return await async_client.post(
        f"/api/v1/prescriptions/{pid}/transition",
        json={"to": to, **extra},
        headers=headers,
    )


@pytest.mark.anyio
async def test_full_lifecycle_open_to_verified(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)

    r1 = await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    assert r1.status_code == status.HTTP_200_OK, r1.text
    assert r1.json()["status"] == PrescriptionStatus.IN_PROGRESS.value

    r2 = await _transition(
        async_client, pid, headers, PrescriptionStatus.COMPLETED.value, evidence="photo#42"
    )
    assert r2.status_code == status.HTTP_200_OK, r2.text
    assert r2.json()["evidence"] == "photo#42"

    r3 = await _transition(async_client, pid, headers, PrescriptionStatus.VERIFIED.value)
    assert r3.status_code == status.HTTP_200_OK, r3.text
    assert r3.json()["status"] == PrescriptionStatus.VERIFIED.value
    assert r3.json()["closed_at"] is not None


@pytest.mark.anyio
async def test_invalid_jump_open_to_completed_409(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)

    r = await _transition(
        async_client, pid, headers, PrescriptionStatus.COMPLETED.value, evidence="x"
    )
    assert r.status_code == status.HTTP_409_CONFLICT
    assert r.json()["detail"]["code"] == "prescription_invalid_transition"


@pytest.mark.anyio
async def test_complete_without_evidence_422(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)

    r = await _transition(async_client, pid, headers, PrescriptionStatus.COMPLETED.value)
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert r.json()["detail"]["code"] == "evidence_required"


@pytest.mark.anyio
async def test_verify_forbidden_for_non_admin_403(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    admin = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, admin, company_id, site_id)
    await _transition(async_client, pid, admin, PrescriptionStatus.IN_PROGRESS.value)
    await _transition(
        async_client, pid, admin, PrescriptionStatus.COMPLETED.value, evidence="ok"
    )

    lm = await make_auth_headers(RoleEnum.LINE_MANAGER)
    r = await _transition(async_client, pid, lm, PrescriptionStatus.VERIFIED.value)
    assert r.status_code == status.HTTP_403_FORBIDDEN
    assert r.json()["detail"]["code"] == "prescription_verify_forbidden"


@pytest.mark.anyio
async def test_failed_verification_rework_completed_to_in_progress(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    await _transition(
        async_client, pid, headers, PrescriptionStatus.COMPLETED.value, evidence="ok"
    )

    r = await _transition(
        async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value, note="rework"
    )
    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["status"] == PrescriptionStatus.IN_PROGRESS.value
    assert r.json()["closed_at"] is None


@pytest.mark.anyio
async def test_cancel_stamps_closed_at(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    r = await _transition(async_client, pid, headers, PrescriptionStatus.CANCELLED.value)
    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["closed_at"] is not None


@pytest.mark.anyio
async def test_patch_cannot_move_status(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)

    # 'status' is not a field on PrescriptionUpdate; pydantic ignores it.
    r = await async_client.patch(
        f"/api/v1/prescriptions/{pid}",
        json={"status": PrescriptionStatus.VERIFIED.value, "description": "edited"},
        headers=headers,
    )
    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["status"] == PrescriptionStatus.OPEN.value  # unchanged
    assert r.json()["description"] == "edited"


@pytest.mark.anyio
async def test_transition_writes_audit_row(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)

    async with sessionmaker() as session:
        logs = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "prescription",
                    AuditLog.object_id == pid,
                    AuditLog.action == "transition",
                )
            )
        ).scalars().all()
        assert logs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/api/test_prescriptions_lifecycle_api.py -p no:cacheprovider -q`
Expected: FAIL — `404 Not Found` for `/transition` (endpoint absent) / create still accepts no status path. (Slow: boots the app.)

- [ ] **Step 3: Update imports in `prescriptions.py`**

At the top of `backend/app/api/routes/prescriptions.py`, add:

```python
from datetime import datetime, timezone
```

and extend the schema import to include `PrescriptionTransition`, and add the FSM import:

```python
from app.schemas.prescriptions import (
    PrescriptionCreate,
    PrescriptionPage,
    PrescriptionRead,
    PrescriptionTransition,
    PrescriptionUpdate,
)
from app.domains.prescriptions.lifecycle import (
    InvalidTransition,
    VERIFY_ROLES,
    is_terminal,
    requires_evidence,
    validate_transition,
)
```

- [ ] **Step 4: Force OPEN on create**

In `create_prescription`, delete the `status=payload.status,` line from the `Prescription(...)` constructor. The model defaults `status` to `PrescriptionStatus.OPEN`, so new records start OPEN:

```python
    record = Prescription(
        tenant_id=str(tenant.id),
        inspection_id=payload.inspection_id,
        incident_id=payload.incident_id,
        description=payload.description,
        due_at=payload.due_at,
        assignee_id=payload.assignee_id,
    )
```

(No other change to `create_prescription`. `PATCH update_prescription` needs **no** code change — `status` is no longer a field on `PrescriptionUpdate`, so the `model_dump(exclude_unset=True)` loop can't set it.)

- [ ] **Step 5: Add the transition endpoint**

Append after `update_prescription` in `backend/app/api/routes/prescriptions.py`:

```python
@router.post("/prescriptions/{prescription_id}/transition", response_model=PrescriptionRead)
async def transition_prescription(
    request: Request,
    prescription_id: str,
    payload: PrescriptionTransition,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await _get_prescription(session, str(tenant.id), prescription_id)
    current = record.status
    target = payload.to

    try:
        validate_transition(current, target)
    except InvalidTransition as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error_detail("prescription_invalid_transition", str(exc)),
        )

    # Idempotent no-op: same state, no write, no audit row.
    if current == target:
        return PrescriptionRead.model_validate(record)

    # Segregation of duties: only admin/owner may verify (повторная проверка).
    if target == PrescriptionStatus.VERIFIED:
        roles = {value.lower() for value in access.to_auth_context().roles}
        if not roles & VERIFY_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=_error_detail(
                    "prescription_verify_forbidden",
                    "Only admin or owner may verify prescriptions",
                ),
            )

    # Evidence is required to mark a prescription completed (payload or stored).
    effective_evidence = payload.evidence if payload.evidence is not None else record.evidence
    if requires_evidence(target) and not (effective_evidence and effective_evidence.strip()):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail(
                "evidence_required", "Evidence is required to complete a prescription"
            ),
        )

    record.status = target
    if payload.evidence is not None:
        record.evidence = payload.evidence
    if is_terminal(target):
        record.closed_at = datetime.now(timezone.utc)

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="transition",
        object_type="prescription",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={
            "from": current.value,
            "to": target.value,
            "evidence_present": bool(record.evidence),
            "note": payload.note,
        },
    )
    await session.commit()
    await session.refresh(record)
    return PrescriptionRead.model_validate(record)
```

- [ ] **Step 6: Run the API test to verify it passes**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/api/test_prescriptions_lifecycle_api.py -p no:cacheprovider -q`
Expected: PASS (8 passed; slow). If a fixture/endpoint mismatch surfaces, apply the Executor note in Step 1.

- [ ] **Step 7: Migrate the existing integration test**

In `tests/integration/test_prescriptions_api.py::test_prescription_crud_and_audit`, replace the single `OPEN→COMPLETED` PATCH block (currently ~lines 49-55) with the valid transition path:

```python
    # Status now moves only through /transition, following the FSM.
    move_in_progress = await async_client.post(
        f"/api/v1/prescriptions/{prescription_id}/transition",
        json={"to": PrescriptionStatus.IN_PROGRESS.value},
        headers=headers,
    )
    assert move_in_progress.status_code == 200, move_in_progress.text

    complete = await async_client.post(
        f"/api/v1/prescriptions/{prescription_id}/transition",
        json={"to": PrescriptionStatus.COMPLETED.value, "evidence": "corrective plan attached"},
        headers=headers,
    )
    assert complete.status_code == 200, complete.text
    assert complete.json()["status"] == PrescriptionStatus.COMPLETED.value
```

- [ ] **Step 8: Run the migrated integration test**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/integration/test_prescriptions_api.py -p no:cacheprovider -q`
Expected: PASS (2 passed; slow).

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/routes/prescriptions.py tests/api/test_prescriptions_lifecycle_api.py tests/integration/test_prescriptions_api.py
git commit -m "feat(prescriptions): /transition FSM endpoint + create forces OPEN; migrate status test (TZ-3.4-V12-01)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Docs — acceptance scenarios + coverage matrix row

**Files:**
- Create: `docs/acceptance/prescriptions-lifecycle.md`
- Modify: `docs/audit/TZ_COVERAGE_MATRIX.md` (row `TZ-3.4-V12-01`, currently line ~35)

- [ ] **Step 1: Write the acceptance doc**

```markdown
# Acceptance — Prescriptions lifecycle (TZ-3.4-V12-01)

Status moves only through `POST /api/v1/prescriptions/{id}/transition`. FSM:
`OPEN → IN_PROGRESS → COMPLETED → VERIFIED` (terminal); `COMPLETED → IN_PROGRESS`
on a failed re-inspection; `CANCELLED` reachable from `OPEN`/`IN_PROGRESS`.

## Scenarios

1. **Happy path.** Create (OPEN) → transition IN_PROGRESS (200) → COMPLETED with
   `evidence` (200) → VERIFIED as admin/owner (200; `closed_at` set).
2. **Invalid jump.** OPEN → COMPLETED → **409** `prescription_invalid_transition`.
3. **Evidence gate.** IN_PROGRESS → COMPLETED without `evidence` → **422**
   `evidence_required`.
4. **Segregation of duties.** COMPLETED → VERIFIED by a non-admin/owner (e.g.
   `line_manager`) → **403** `prescription_verify_forbidden`.
5. **Rework.** COMPLETED → IN_PROGRESS (failed re-inspection) → 200; `closed_at`
   stays null.
6. **Cancel.** OPEN/IN_PROGRESS → CANCELLED → 200; `closed_at` set.
7. **PATCH cannot move status.** `PATCH` with a `status` field is ignored (200,
   status unchanged); field edits (description/due_at/assignee) still apply.

## Deferred (separate increments)
Escalations (overdue → notify), closure-rate (% закрытия) aggregate, file-bound
evidence, and per-user verifier ≠ assignee identity checks.
```

- [ ] **Step 2: Update the matrix row**

Replace the `TZ-3.4-V12-01` row in `docs/audit/TZ_COVERAGE_MATRIX.md`. Old plan cell reads `Finalize lifecycle/status workflow and acceptance docs`; the row stays `partial`. New row (keep exactly 11 pipe-separated cells, no `|` inside a cell):

```
| TZ-3.4-V12-01 | [v1.2] Prescriptions skeleton | backend/app/api/routes/prescriptions.py (/prescriptions/{id}/transition), backend/app/domains/prescriptions/lifecycle.py | backend/app/migrations/versions/20260530_wa03_prescription_lifecycle.py | - | - | frontend/src/pages/prescriptions | backend/tests/test_prescription_lifecycle.py, backend/tests/test_wa03_prescription_lifecycle_migration.py, tests/api/test_prescriptions_lifecycle_api.py, backend/tests/test_prescriptions_access_parity.py | partial | p2 | Status FSM + evidence + verification (segregated to admin/owner) shipped; escalations + closure-rate (% закрытия) deferred → P10 |
```

- [ ] **Step 3: Validate the matrix**

Run: `& ".venv\Scripts\python.exe" scripts/audit/check_tz_coverage_matrix.py`
Expected: `TZ coverage matrix validation passed: 46 rows ...`.

- [ ] **Step 4: Commit**

```bash
git add docs/acceptance/prescriptions-lifecycle.md docs/audit/TZ_COVERAGE_MATRIX.md
git commit -m "docs(prescriptions): lifecycle acceptance scenarios + matrix row (TZ-3.4-V12-01)" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] **App-free suite** (safe on Py3.13/Win):
  Run: `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescription_lifecycle_model.py backend/tests/test_prescription_lifecycle.py backend/tests/test_wa03_prescription_lifecycle_migration.py backend/tests/test_prescription_schemas.py -p no:cacheprovider -q`
  Expected: all green.
- [ ] **App-booting suite** (slow; CI-canonical on 3.12.12):
  Run: `& ".venv\Scripts\python.exe" -m pytest tests/api/test_prescriptions_lifecycle_api.py tests/integration/test_prescriptions_api.py -p no:cacheprovider -q`
  Expected: all green.
- [ ] **Matrix validator:** `& ".venv\Scripts\python.exe" scripts/audit/check_tz_coverage_matrix.py` → 46 rows valid.
- [ ] **Access-parity regression:** `& ".venv\Scripts\python.exe" -m pytest backend/tests/test_prescriptions_access_parity.py -p no:cacheprovider -q` (confirm the existing RBAC parity test still passes).

## Out of scope (deferred — do NOT implement here)
Escalations (overdue → notify/flag), closure-rate (% закрытия) aggregate endpoint,
file-attachment-bound evidence, and per-user verifier ≠ assignee identity checks.
These are tracked as future increments per the spec §10.
