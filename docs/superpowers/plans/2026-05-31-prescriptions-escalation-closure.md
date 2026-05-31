# Prescriptions Escalation + Closure-Rate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close `TZ-3.4-V12-01` from `partial` to `done` by adding overdue escalations (on-demand endpoints + a daily beat sweep, reusing the `TASK_OVERDUE` outbox event) and a closure-rate (`% закрытия`) summary to the prescriptions module.

**Architecture:** Pure FSM/metric helpers in `app/domains/prescriptions/lifecycle.py`; a thin I/O service in `app/domains/prescriptions/service.py` (overdue query, notify-via-outbox, status summary); three additive endpoints on the existing prescriptions router; an `is_overdue` flag on `PrescriptionRead`; a beat task `prescriptions.escalate.tick` that mirrors the proven `reminders.scan` tenant-iteration shape. **No migration** — columns (`due_at`, `closed_at`) and indexes (`ix_prescription_status`, `ix_prescription_due`) already exist. Additive only — no existing contract changes.

**Tech Stack:** Python 3.12 (CI canonical; local Py3.13/Win), FastAPI, SQLAlchemy 2.0 async, Pydantic v2, Celery + crontab beat, pytest / pytest-asyncio.

**Spec:** [`docs/superpowers/specs/2026-05-31-prescriptions-escalation-closure-design.md`](../specs/2026-05-31-prescriptions-escalation-closure-design.md)

**Branch:** `feat/wa-prescriptions-escalation` (already created off `main`).

**Test command convention** (per `CLAUDE.md`): prefer `python3.12 -m pytest …`; if 3.12 is absent locally, run with `python -m pytest …` (the repo `.venv`, Py3.13/Win) and note the version — CI on 3.12.12 is canonical. App-free files (unit, task-registration) run clean locally; app-booting files (`tests/api/…`) run single-file locally.

---

## File Structure

**Create:**
- `backend/app/domains/prescriptions/service.py` — I/O service: `list_overdue`, `notify_overdue`, `status_summary`.
- `backend/tests/test_prescription_escalation.py` — app-free unit tests for the pure helpers.
- `tests/api/test_prescriptions_escalation_api.py` — app-booting API contract tests.
- `backend/tests/test_prescriptions_escalate_tick.py` — app-free beat-registration tests.

**Modify:**
- `backend/app/domains/prescriptions/lifecycle.py` — add pure `is_overdue` + `closure_rate`.
- `backend/app/schemas/prescriptions.py` — add `is_overdue` to `PrescriptionRead`; add `PrescriptionSummary`.
- `backend/app/api/routes/prescriptions.py` — add `_to_read` helper; route all reads through it; add 3 endpoints (`GET /overdue`, `GET /summary`, `POST /remind-overdue`) **before** `GET /{prescription_id}`.
- `backend/app/tasks/_core.py` — add `prescriptions.escalate.tick` task + async core.
- `backend/app/services/celery_app.py` — register `prescriptions-escalate-daily` in `beat_schedule`.
- `docs/audit/TZ_COVERAGE_MATRIX.md` — `TZ-3.4-V12-01` `partial → done`; clarify `TZ-6.3-V11-01` note.
- `docs/acceptance/prescriptions-lifecycle.md` — append overdue + closure-rate scenarios.

---

## Task 1: Pure helpers — `is_overdue` + `closure_rate`

**Files:**
- Modify: `backend/app/domains/prescriptions/lifecycle.py`
- Test: `backend/tests/test_prescription_escalation.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prescription_escalation.py`:

```python
"""Unit tests for prescription escalation/closure helpers (TZ-3.4-V12-01). App-free."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domains.prescriptions.lifecycle import closure_rate, is_overdue
from app.models.models import PrescriptionStatus as S

TODAY = date(2026, 5, 31)


@pytest.mark.parametrize(
    "due,status,expected",
    [
        (TODAY - timedelta(days=1), S.OPEN, True),
        (TODAY - timedelta(days=1), S.IN_PROGRESS, True),
        (TODAY - timedelta(days=1), S.COMPLETED, True),   # done-but-unverified, past due => overdue
        (TODAY - timedelta(days=1), S.VERIFIED, False),   # terminal => never overdue
        (TODAY - timedelta(days=1), S.CANCELLED, False),  # terminal => never overdue
        (TODAY, S.OPEN, False),                           # due today is not yet past due
        (TODAY + timedelta(days=1), S.OPEN, False),
        (None, S.OPEN, False),                            # no deadline => not overdue
    ],
)
def test_is_overdue(due, status, expected) -> None:
    assert is_overdue(due, status, TODAY) is expected


def test_closure_rate_counts_verified_and_completed_over_total() -> None:
    counts = {S.OPEN: 1, S.IN_PROGRESS: 1, S.COMPLETED: 2, S.VERIFIED: 2, S.CANCELLED: 0}
    # closed = completed(2) + verified(2) = 4 ; total = 6
    assert closure_rate(counts) == pytest.approx(4 / 6)


def test_closure_rate_zero_when_empty() -> None:
    assert closure_rate({}) == 0.0
    assert closure_rate({S.OPEN: 0, S.CANCELLED: 0}) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_prescription_escalation.py -v`
Expected: FAIL — `ImportError: cannot import name 'closure_rate'` (and `is_overdue`).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/domains/prescriptions/lifecycle.py`, update the imports at the top and append the two helpers.

Change the import block (currently `from app.models.models import PrescriptionStatus`) to:

```python
from collections.abc import Mapping
from datetime import date

from app.models.models import PrescriptionStatus
```

Append at the end of the file (after `requires_evidence`):

```python
def is_overdue(due_at: date | None, status: PrescriptionStatus, today: date) -> bool:
    """True when the prescription is past its deadline and not yet closed.

    Terminal states (VERIFIED, CANCELLED) are never overdue. A COMPLETED row
    past its deadline IS overdue — work is done but not yet verified/closed.
    `today` is injected so callers/tests stay deterministic.
    """
    return due_at is not None and due_at < today and status not in TERMINAL_STATES


def closure_rate(counts: Mapping[PrescriptionStatus, int]) -> float:
    """(VERIFIED + COMPLETED) / total ; 0.0 when there are no prescriptions."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    closed = counts.get(PrescriptionStatus.VERIFIED, 0) + counts.get(PrescriptionStatus.COMPLETED, 0)
    return closed / total
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_prescription_escalation.py -v`
Expected: PASS (all parametrized cases + both closure-rate tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/prescriptions/lifecycle.py backend/tests/test_prescription_escalation.py
git commit -m "feat(prescriptions): pure is_overdue + closure_rate helpers (TZ-3.4-V12-01)"
```

---

## Task 2: `is_overdue` on `PrescriptionRead` + `_to_read` helper

**Files:**
- Modify: `backend/app/schemas/prescriptions.py`
- Modify: `backend/app/api/routes/prescriptions.py`
- Test: `tests/api/test_prescriptions_escalation_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_prescriptions_escalation_api.py` with shared helpers + the first test:

```python
"""API contract for prescription escalation + closure-rate (TZ-3.4-V12-01):
is_overdue flag, /overdue, /summary, /remind-overdue.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import AuditLog, Outbox, PrescriptionStatus, RoleEnum
from app.services.events import EventType


async def _seed_company_site(sessionmaker, data_factory) -> tuple[str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()
        return company.id, site.id


async def _seed_prescription(
    async_client, headers, company_id: str, site_id: str, *, due_at: date | None = None,
    description: str = "Fix guardrail",
) -> str:
    insp = await async_client.post(
        "/api/v1/inspections",
        json={
            "company_id": company_id,
            "site_id": site_id,
            "authority": "Ростехнадзор",
            "scheduled_at": date.today().isoformat(),
        },
        headers=headers,
    )
    assert insp.status_code == status.HTTP_201_CREATED, insp.text
    body = {"inspection_id": insp.json()["id"], "description": description}
    if due_at is not None:
        body["due_at"] = due_at.isoformat()
    r = await async_client.post("/api/v1/prescriptions", json=body, headers=headers)
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_is_overdue_flag_reflects_due_date(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid_past = await _seed_prescription(
        async_client, headers, company_id, site_id, due_at=date.today() - timedelta(days=1)
    )
    pid_future = await _seed_prescription(
        async_client, headers, company_id, site_id, due_at=date.today() + timedelta(days=1)
    )

    r_past = await async_client.get(f"/api/v1/prescriptions/{pid_past}", headers=headers)
    assert r_past.status_code == status.HTTP_200_OK, r_past.text
    assert r_past.json()["is_overdue"] is True

    r_future = await async_client.get(f"/api/v1/prescriptions/{pid_future}", headers=headers)
    assert r_future.json()["is_overdue"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_is_overdue_flag_reflects_due_date -v`
Expected: FAIL — `KeyError: 'is_overdue'` (field not in the response yet).

- [ ] **Step 3: Write minimal implementation**

(3a) In `backend/app/schemas/prescriptions.py`, add `is_overdue` to `PrescriptionRead` (after `created_at`/`updated_at`):

```python
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
    is_overdue: bool = False
```

(3b) In `backend/app/api/routes/prescriptions.py`:

Change the datetime import (line 5) to include `date`:

```python
from datetime import date, datetime, timezone
```

Add `is_overdue` to the lifecycle import block (lines ~20-26):

```python
from app.domains.prescriptions.lifecycle import (
    VERIFY_ROLES,
    InvalidTransition,
    is_overdue,
    is_terminal,
    requires_evidence,
    validate_transition,
)
```

Add the serialization helper next to `_error_detail` (after line ~48):

```python
def _to_read(record: Prescription, *, today: date) -> PrescriptionRead:
    """Serialize a prescription with a today-relative is_overdue flag."""
    return PrescriptionRead.model_validate(record).model_copy(
        update={"is_overdue": is_overdue(record.due_at, record.status, today)}
    )
```

Now route every read through `_to_read`. Replace each `PrescriptionRead.model_validate(...)` call:

- In `list_prescriptions`, before building the response add `today = datetime.now(timezone.utc).date()` (e.g. right after `TenantContextValidator.ensure_tenant_context(tenant)`), then change the return items:
  ```python
      return PrescriptionPage(
          items=[_to_read(item, today=today) for item in items],
          total=int(total or 0),
      )
  ```
- In `create_prescription` (final return):
  ```python
      return _to_read(record, today=datetime.now(timezone.utc).date())
  ```
- In `get_prescription` (final return):
  ```python
      return _to_read(record, today=datetime.now(timezone.utc).date())
  ```
- In `update_prescription` (final return):
  ```python
      return _to_read(record, today=datetime.now(timezone.utc).date())
  ```
- In `transition_prescription`, the idempotent no-op return:
  ```python
      if current == target:
          return _to_read(record, today=datetime.now(timezone.utc).date())
  ```
- In `transition_prescription`, the final return:
  ```python
      return _to_read(record, today=datetime.now(timezone.utc).date())
  ```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_is_overdue_flag_reflects_due_date -v`
Expected: PASS.

Also confirm the existing lifecycle suite still passes (no regression in the reads):
Run: `python -m pytest tests/api/test_prescriptions_lifecycle_api.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/prescriptions.py backend/app/api/routes/prescriptions.py tests/api/test_prescriptions_escalation_api.py
git commit -m "feat(prescriptions): is_overdue on PrescriptionRead via _to_read helper"
```

---

## Task 3: Service `list_overdue` + `GET /prescriptions/overdue`

**Files:**
- Create: `backend/app/domains/prescriptions/service.py`
- Modify: `backend/app/api/routes/prescriptions.py`
- Test: `tests/api/test_prescriptions_escalation_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_prescriptions_escalation_api.py`:

```python
@pytest.mark.asyncio
async def test_overdue_lists_only_past_due_non_terminal(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    past = date.today() - timedelta(days=2)

    pid_overdue = await _seed_prescription(async_client, headers, company_id, site_id, due_at=past)
    await _seed_prescription(  # future -> not overdue
        async_client, headers, company_id, site_id, due_at=date.today() + timedelta(days=2)
    )
    pid_cancelled = await _seed_prescription(async_client, headers, company_id, site_id, due_at=past)
    await async_client.post(
        f"/api/v1/prescriptions/{pid_cancelled}/transition",
        json={"to": PrescriptionStatus.CANCELLED.value},
        headers=headers,
    )

    r = await async_client.get("/api/v1/prescriptions/overdue", headers=headers)
    assert r.status_code == status.HTTP_200_OK, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert pid_overdue in ids
    assert pid_cancelled not in ids  # terminal excluded
    assert all(item["is_overdue"] for item in r.json()["items"])


@pytest.mark.asyncio
async def test_overdue_requires_prescription_role_403(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.WORKER)  # not in {admin,owner,hr,line_manager}
    r = await async_client.get("/api/v1/prescriptions/overdue", headers=headers)
    assert r.status_code == status.HTTP_403_FORBIDDEN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_overdue_lists_only_past_due_non_terminal -v`
Expected: FAIL — `404` with `prescription_not_found` (the path `/overdue` is currently captured by `GET /{prescription_id}`), so the JSON has no `items`.

- [ ] **Step 3: Write minimal implementation**

(3a) Create `backend/app/domains/prescriptions/service.py`:

```python
"""I/O service for prescription escalation + closure-rate (TZ-3.4-V12-01)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.prescriptions.lifecycle import TERMINAL_STATES, closure_rate
from app.models.models import Prescription, PrescriptionStatus
from app.services.events import EventType
from app.services.outbox import OutboxService


async def list_overdue(
    session: AsyncSession, *, tenant_id: str, today: date
) -> list[Prescription]:
    """Tenant-scoped prescriptions past their deadline and not yet closed."""
    stmt = (
        select(Prescription)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.deleted_at.is_(None),
            Prescription.due_at.is_not(None),
            Prescription.due_at < today,
            Prescription.status.not_in(list(TERMINAL_STATES)),
        )
        .order_by(Prescription.due_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())
```

(3b) In `backend/app/api/routes/prescriptions.py`, import the service functions (after the lifecycle import block):

```python
from app.domains.prescriptions.service import list_overdue
```

Add the endpoint **immediately before** `@router.get("/prescriptions/{prescription_id}", ...)` (so the literal path is not captured by the id route):

```python
@router.get("/prescriptions/overdue", response_model=PrescriptionPage)
async def list_overdue_prescriptions(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> PrescriptionPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    items = await list_overdue(session, tenant_id=str(tenant.id), today=today)
    return PrescriptionPage(
        items=[_to_read(item, today=today) for item in items],
        total=len(items),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_overdue_lists_only_past_due_non_terminal tests/api/test_prescriptions_escalation_api.py::test_overdue_requires_prescription_role_403 -v`
Expected: PASS (both). Passing the first proves route ordering is correct (`/overdue` was not captured as an id).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/prescriptions/service.py backend/app/api/routes/prescriptions.py tests/api/test_prescriptions_escalation_api.py
git commit -m "feat(prescriptions): GET /prescriptions/overdue (service.list_overdue)"
```

---

## Task 4: Service `status_summary` + `GET /prescriptions/summary`

**Files:**
- Modify: `backend/app/domains/prescriptions/service.py`
- Modify: `backend/app/schemas/prescriptions.py`
- Modify: `backend/app/api/routes/prescriptions.py`
- Test: `tests/api/test_prescriptions_escalation_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_prescriptions_escalation_api.py`:

```python
@pytest.mark.asyncio
async def test_summary_breakdown_and_closure_rate(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    # OPEN (left as-is)
    await _seed_prescription(async_client, headers, company_id, site_id)
    # COMPLETED
    pid_c = await _seed_prescription(async_client, headers, company_id, site_id)
    await async_client.post(f"/api/v1/prescriptions/{pid_c}/transition",
                            json={"to": "in_progress"}, headers=headers)
    await async_client.post(f"/api/v1/prescriptions/{pid_c}/transition",
                            json={"to": "completed", "evidence": "e"}, headers=headers)
    # VERIFIED
    pid_v = await _seed_prescription(async_client, headers, company_id, site_id)
    await async_client.post(f"/api/v1/prescriptions/{pid_v}/transition",
                            json={"to": "in_progress"}, headers=headers)
    await async_client.post(f"/api/v1/prescriptions/{pid_v}/transition",
                            json={"to": "completed", "evidence": "e"}, headers=headers)
    await async_client.post(f"/api/v1/prescriptions/{pid_v}/transition",
                            json={"to": "verified"}, headers=headers)

    r = await async_client.get("/api/v1/prescriptions/summary", headers=headers)
    assert r.status_code == status.HTTP_200_OK, r.text
    body = r.json()
    bs = body["by_status"]
    # all five statuses are present as keys
    assert set(bs) == {"open", "in_progress", "completed", "verified", "cancelled"}
    # at least the three we seeded
    assert bs["open"] >= 1 and bs["completed"] >= 1 and bs["verified"] >= 1
    # internal consistency: total == sum, closure_rate == (verified+completed)/total
    assert body["total"] == sum(bs.values())
    assert body["closure_rate"] == pytest.approx((bs["verified"] + bs["completed"]) / body["total"])
    assert body["overdue_count"] >= 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_summary_breakdown_and_closure_rate -v`
Expected: FAIL — `404`/`prescription_not_found` (no `/summary` route yet → captured by `/{prescription_id}`).

- [ ] **Step 3: Write minimal implementation**

(3a) In `backend/app/schemas/prescriptions.py`, add the summary schema (after `PrescriptionPage`):

```python
class PrescriptionSummary(BaseSchema):
    by_status: dict[str, int]
    total: int
    overdue_count: int
    closure_rate: float
```

(3b) In `backend/app/domains/prescriptions/service.py`, append:

```python
async def status_summary(
    session: AsyncSession, *, tenant_id: str, today: date
) -> dict[str, object]:
    """Per-status counts + overdue_count + closure_rate for a tenant."""
    rows = (
        await session.execute(
            select(Prescription.status, func.count())
            .where(
                Prescription.tenant_id == tenant_id,
                Prescription.deleted_at.is_(None),
            )
            .group_by(Prescription.status)
        )
    ).all()
    counts: dict[PrescriptionStatus, int] = {s: 0 for s in PrescriptionStatus}
    for status_value, n in rows:
        counts[status_value] = int(n)

    overdue_count = await session.scalar(
        select(func.count())
        .select_from(Prescription)
        .where(
            Prescription.tenant_id == tenant_id,
            Prescription.deleted_at.is_(None),
            Prescription.due_at.is_not(None),
            Prescription.due_at < today,
            Prescription.status.not_in(list(TERMINAL_STATES)),
        )
    )
    return {
        "by_status": {s.value: counts[s] for s in PrescriptionStatus},
        "total": sum(counts.values()),
        "overdue_count": int(overdue_count or 0),
        "closure_rate": closure_rate(counts),
    }
```

(3c) In `backend/app/api/routes/prescriptions.py`, extend the schema import (lines ~29-35) with `PrescriptionSummary`:

```python
from app.schemas.prescriptions import (
    PrescriptionCreate,
    PrescriptionPage,
    PrescriptionRead,
    PrescriptionSummary,
    PrescriptionTransition,
    PrescriptionUpdate,
)
```

Extend the service import with `status_summary`:

```python
from app.domains.prescriptions.service import list_overdue, status_summary
```

Add the endpoint **immediately before** `@router.get("/prescriptions/{prescription_id}", ...)` (next to the overdue route):

```python
@router.get("/prescriptions/summary", response_model=PrescriptionSummary)
async def prescriptions_summary(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> PrescriptionSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    data = await status_summary(session, tenant_id=str(tenant.id), today=today)
    return PrescriptionSummary(**data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_summary_breakdown_and_closure_rate -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/prescriptions/service.py backend/app/schemas/prescriptions.py backend/app/api/routes/prescriptions.py tests/api/test_prescriptions_escalation_api.py
git commit -m "feat(prescriptions): GET /prescriptions/summary with closure-rate"
```

---

## Task 5: Service `notify_overdue` + `POST /prescriptions/remind-overdue`

**Files:**
- Modify: `backend/app/domains/prescriptions/service.py`
- Modify: `backend/app/api/routes/prescriptions.py`
- Test: `tests/api/test_prescriptions_escalation_api.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_prescriptions_escalation_api.py`:

```python
@pytest.mark.asyncio
async def test_remind_overdue_emits_task_overdue_with_stable_key(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    past = date.today() - timedelta(days=3)
    pid = await _seed_prescription(async_client, headers, company_id, site_id, due_at=past)

    r1 = await async_client.post("/api/v1/prescriptions/remind-overdue", headers=headers)
    assert r1.status_code == status.HTTP_200_OK, r1.text
    assert r1.json()["count"] >= 1

    expected_key = f"prescription-overdue:{pid}:{past.isoformat()}"
    async with sessionmaker() as session:
        rows = (
            await session.execute(
                select(Outbox).where(
                    Outbox.event_type == EventType.TASK_OVERDUE.value,
                    Outbox.idempotency_key == expected_key,
                )
            )
        ).scalars().all()
        assert rows, "expected a TASK_OVERDUE outbox row for the overdue prescription"

    # second same-day call: the idempotency key is stable (destination-scoped dedup-ready)
    await async_client.post("/api/v1/prescriptions/remind-overdue", headers=headers)
    async with sessionmaker() as session:
        keys = (
            await session.execute(
                select(Outbox.idempotency_key).where(Outbox.idempotency_key == expected_key)
            )
        ).scalars().all()
        assert set(keys) == {expected_key}  # every emission shares one stable key

    # audit trail
    async with sessionmaker() as session:
        logs = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "prescription",
                    AuditLog.action == "notify_overdue",
                )
            )
        ).scalars().all()
        assert logs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_remind_overdue_emits_task_overdue_with_stable_key -v`
Expected: FAIL — `404 Not Found` (no `/remind-overdue` route yet).

- [ ] **Step 3: Write minimal implementation**

(3a) In `backend/app/domains/prescriptions/service.py`, append:

```python
async def notify_overdue(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, today: date
) -> list[Prescription]:
    """Enqueue a TASK_OVERDUE outbox event for each overdue prescription.

    The idempotency key embeds the due date, so re-running on the same day
    dedups at the destination (mirrors briefings overdue reminders).
    """
    overdue = await list_overdue(session, tenant_id=tenant_id, today=today)
    if not overdue:
        return []
    outbox = OutboxService(session)
    for p in overdue:
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=EventType.TASK_OVERDUE.value,
            idempotency_key=f"prescription-overdue:{p.id}:{p.due_at.isoformat()}",
            payload={
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "task_id": p.id,
                "title": f"Prescription overdue: {p.description[:80]}",
                "due_at": p.due_at,
                "assignee_id": p.assignee_id,
                "status": p.status.value,
                "priority": "high",
                "overdue": True,
            },
        )
    return overdue
```

(3b) In `backend/app/api/routes/prescriptions.py`, extend the service import with `notify_overdue`:

```python
from app.domains.prescriptions.service import list_overdue, notify_overdue, status_summary
```

Add the endpoint next to the other new routes (a POST — no `/{id}` collision, but keep it grouped):

```python
@router.post("/prescriptions/remind-overdue")
async def remind_overdue_prescriptions(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, object]:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    actor_id = getattr(access.user, "id", None)
    overdue = await notify_overdue(
        session, tenant_id=str(tenant.id), actor_id=actor_id, today=today
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="notify_overdue",
        object_type="prescription",
        object_id="bulk",
        user_id=actor_id,
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"count": len(overdue)},
    )
    await session.commit()
    return {
        "count": len(overdue),
        "items": [_to_read(p, today=today) for p in overdue],
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py::test_remind_overdue_emits_task_overdue_with_stable_key -v`
Expected: PASS.

Then run the whole escalation API file to confirm no cross-test interference:
Run: `python -m pytest tests/api/test_prescriptions_escalation_api.py -v`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/prescriptions/service.py backend/app/api/routes/prescriptions.py tests/api/test_prescriptions_escalation_api.py
git commit -m "feat(prescriptions): POST /prescriptions/remind-overdue emits TASK_OVERDUE"
```

---

## Task 6: Beat task `prescriptions.escalate.tick` (daily sweep)

**Files:**
- Modify: `backend/app/tasks/_core.py`
- Modify: `backend/app/services/celery_app.py`
- Test: `backend/tests/test_prescriptions_escalate_tick.py`

> **Note on test depth:** the per-tenant notify behavior is already covered by Task 5's `/remind-overdue` test (same `notify_overdue` service function). The beat task's only added logic is tenant iteration, which mirrors the proven `_scan_reminders_job`. This task therefore verifies **registration + wiring** deterministically (app-free), rather than a flaky multi-tenant eager run (left to CI/integration).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_prescriptions_escalate_tick.py`:

```python
"""Registration/wiring tests for the prescriptions escalation beat task. App-free."""
from __future__ import annotations

from app.services.celery_app import celery_app
from app.tasks import _core  # noqa: F401  -- importing registers @celery_app.task decorators


def test_beat_schedule_registers_daily_escalation() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "prescriptions-escalate-daily" in schedule
    entry = schedule["prescriptions-escalate-daily"]
    assert entry["task"] == "prescriptions.escalate.tick"
    # crontab(hour=2, minute=0) -> .hour and .minute are sets of ints
    assert 2 in entry["schedule"].hour
    assert 0 in entry["schedule"].minute


def test_escalation_task_is_registered() -> None:
    assert "prescriptions.escalate.tick" in celery_app.tasks
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_prescriptions_escalate_tick.py -v`
Expected: FAIL — `KeyError: 'prescriptions-escalate-daily'` (and the task is not registered).

- [ ] **Step 3: Write minimal implementation**

(3a) In `backend/app/tasks/_core.py`, add the task + async core near the other `@celery_app.task` definitions (e.g. just after `workflow_timers_tick`). The helpers used (`AsyncSessionLocal`, `settings`, `select`, `Tenant`, `tenant_context`, `ensure_tenant_schema`, `session_scope`, `_resolve_task_tenant_scope`, `_run_coroutine`, `RETRYABLE_EXCEPTIONS`, `datetime`, `timezone`) are already imported in this module:

```python
@celery_app.task(
    name="prescriptions.escalate.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def prescriptions_escalate_tick() -> int:
    return _run_coroutine(_prescriptions_escalate_tick())


async def _prescriptions_escalate_tick() -> int:
    # imported lazily to avoid import cycles at task-module load time
    from app.domains.prescriptions.service import notify_overdue

    today = datetime.now(tz=timezone.utc).date()
    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all()
        )
    processed = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                overdue = await notify_overdue(
                    session, tenant_id=tenant_id, actor_id=None, today=today
                )
                await session.commit()
                processed += len(overdue)
    return processed
```

(3b) In `backend/app/services/celery_app.py`, add the entry to `beat_schedule` (lines ~56-65):

```python
celery_app.conf.beat_schedule = {
    "tasks-reminders-daily": {
        "task": "tasks.reminders.dispatch",
        "schedule": crontab(hour=2, minute=0),
    },
    "reminders-scan-hourly": {
        "task": "reminders.scan",
        "schedule": crontab(minute=0),
    },
    "prescriptions-escalate-daily": {
        "task": "prescriptions.escalate.tick",
        "schedule": crontab(hour=2, minute=0),
    },
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_prescriptions_escalate_tick.py -v`
Expected: PASS (both tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/_core.py backend/app/services/celery_app.py backend/tests/test_prescriptions_escalate_tick.py
git commit -m "feat(prescriptions): daily prescriptions.escalate.tick beat sweep"
```

---

## Task 7: Docs + matrix (`partial → done`)

**Files:**
- Modify: `docs/acceptance/prescriptions-lifecycle.md`
- Modify: `docs/audit/TZ_COVERAGE_MATRIX.md`
- Test (validator): `scripts/audit/check_tz_coverage_matrix.py`

- [ ] **Step 1: Append acceptance scenarios**

Add to the end of `docs/acceptance/prescriptions-lifecycle.md`:

```markdown
## Overdue escalation + closure-rate (added 2026-05-31)

**Overdue listing**
1. Create a prescription with `due_at` in the past (stays `OPEN`).
2. `GET /api/v1/prescriptions/overdue` → it appears; `is_overdue: true`. A
   future-dated or `VERIFIED`/`CANCELLED` prescription does **not** appear.

**On-demand reminder**
3. `POST /api/v1/prescriptions/remind-overdue` → `{ "count": N, "items": [...] }`;
   one `TaskOverdue` outbox event per overdue row, keyed
   `prescription-overdue:{id}:{due_date}`. A second same-day call reuses the
   same key (no duplicate delivery to subscribers); an audit row
   `action=notify_overdue` is written.

**Scheduled escalation**
4. The Celery beat task `prescriptions.escalate.tick` runs daily (02:00),
   iterating active tenants and emitting the same `TaskOverdue` events.

**Closure-rate**
5. `GET /api/v1/prescriptions/summary` → `{ by_status, total, overdue_count,
   closure_rate }`, where `closure_rate = (VERIFIED + COMPLETED) / total`
   (`0.0` when there are no prescriptions).
```

- [ ] **Step 2: Update the coverage matrix**

In `docs/audit/TZ_COVERAGE_MATRIX.md`, edit the `TZ-3.4-V12-01` row:
- `status` column: `partial` → `done`.
- `jobs` column: set to `backend/app/tasks/_core.py (prescriptions.escalate.tick), backend/app/services/celery_app.py (beat)`.
- `events` column: set to `backend/app/services/outbox.py (TASK_OVERDUE)`.
- Append to the `backend` column: `, backend/app/domains/prescriptions/service.py`.
- Append to the `tests` column: `, tests/api/test_prescriptions_escalation_api.py, backend/tests/test_prescription_escalation.py, backend/tests/test_prescriptions_escalate_tick.py`.
- `plan` column note → `FSM + evidence + verification + overdue escalations (on-demand /remind-overdue + daily prescriptions.escalate.tick, TASK_OVERDUE) + closure-rate (% закрытия) shipped`.

Also clarify the `TZ-6.3-V11-01` row `plan` note (status stays `partial`):
- → `Scoped ratchet gate + 85% North-Star tracker + climb plan shipped; flips to done on W0 (CI re-enable + floor bootstrap) — cannot be closed by code alone`.

- [ ] **Step 3: Run the matrix validator**

Run: `python scripts/audit/check_tz_coverage_matrix.py`
Expected: exit 0 / "valid" (all rows parse; evidence paths well-formed).

If it reports a missing referenced path, correct the path in the row to match a file actually created by this plan, then re-run until green.

- [ ] **Step 4: Run the full new-test set together**

Run: `python -m pytest backend/tests/test_prescription_escalation.py backend/tests/test_prescriptions_escalate_tick.py tests/api/test_prescriptions_escalation_api.py tests/api/test_prescriptions_lifecycle_api.py -v`
Expected: PASS (new unit + registration + escalation API + the pre-existing lifecycle suite — no regression).

- [ ] **Step 5: Commit**

```bash
git add docs/acceptance/prescriptions-lifecycle.md docs/audit/TZ_COVERAGE_MATRIX.md
git commit -m "docs(prescriptions): matrix TZ-3.4-V12-01 -> done; acceptance scenarios"
```

---

## Self-Review

**1. Spec coverage** — every spec section maps to a task:
- §2 decisions (overdue incl. COMPLETED; `(V+C)/total`; daily beat; reuse TASK_OVERDUE; `is_overdue`; no migration) → Tasks 1–6.
- §3 no migration → confirmed; no migration task exists by design.
- §4 pure core → Task 1. §5 service → Tasks 3/4/5. §6 API + route ordering → Tasks 3/4/5 (ordering asserted by Task 3). §7 event → Task 5. §8 schema/`is_overdue` → Task 2. §9 beat task → Task 6.
- §10 tests → Tasks 1 (unit), 2–5 (API), 6 (registration). §11 docs/matrix → Task 7. §12 acceptance criteria → covered across Tasks 2–7.

**2. Placeholder scan** — no `TBD`/`TODO`/"handle edge cases"; every code step shows the actual code; every run step shows the command + expected result.

**3. Type consistency** — `is_overdue(due_at, status, today)` and `closure_rate(counts)` signatures match between Task 1 (definition), the service (Tasks 3–5), and the route helper `_to_read` (Task 2). `notify_overdue(session, *, tenant_id, actor_id, today)`, `list_overdue(session, *, tenant_id, today)`, `status_summary(session, *, tenant_id, today)` are called with the same keyword arguments in the route (Tasks 3–5) and the beat task (Task 6). `PrescriptionSummary` fields (`by_status`, `total`, `overdue_count`, `closure_rate`) match the `status_summary` return dict keys exactly.

**Known environment caveat:** app-booting files (`tests/api/…`) run single-file locally on Py3.13/Win; CI on 3.12.12 is canonical. The `status_summary` API assertions are written to be DB-scope-agnostic (internal consistency + presence), so they hold whether or not the harness gives a pristine per-test DB.
