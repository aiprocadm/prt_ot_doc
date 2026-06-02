# ORM↔Postgres Enum-Label Parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 52 defective native-PG-enum ORM columns (49 in `app/models/*` + 3 in `app/modules/workflow`) bind a string that is a valid `pg_enum` label, so ORM inserts/updates succeed on Postgres (not merely "migrations apply").

**Architecture:** Add a `native_enum()` helper that sets `values_callable` (binds enum `.value` instead of the member NAME); apply it to exactly the 52 Group-A columns whose pg type uses lowercase/`.value` labels; add an `ALTER TYPE … ADD VALUE IF NOT EXISTS` migration for the 4 types still missing some `.value` labels (which also merges the 8 live Alembic heads). Two guard tests pin it: a fast no-PG pin of the 52, and an authoritative `@pytest.mark.db` guard that introspects live `pg_enum` labels.

**Tech Stack:** Python 3.12 (canonical; local 3.13.7), SQLAlchemy 2 (async), Alembic, asyncpg, Postgres 16 (Docker `promtech-cabinet-db-1`), pytest.

**Spec:** `docs/superpowers/specs/2026-06-02-orm-enum-pg-label-parity-design.md` (read the Appendix for the authoritative audit).

---

## Environment & how to run tests

- Python: `D:\Кодинг\Создание платформы по ОТ\.venv\Scripts\python.exe` (local 3.13.7; CI canonical 3.12.12, currently disabled).
- Run pytest via the **PowerShell tool**, setting `PYTHONPATH` to the backend dir, redirecting output to a file then reading it (git-bash hangs on this machine — `[[py313_win_pytest_invocation]]`).
- PG guard tests need Docker PG up and `TEST_PG_ADMIN_URL` set; they use a **throwaway DB** and must **never** touch `cabinet`.

**Fast (no-PG) suite invocation pattern:**
```powershell
$env:PYTHONPATH = "D:\Кодинг\Создание платформы по ОТ\backend"
& "D:\Кодинг\Создание платформы по ОТ\.venv\Scripts\python.exe" -m pytest `
  backend/tests/test_orm_enum_values_callable_parity.py -v `
  *> "D:\Кодинг\Создание платформы по ОТ\_pytest_out.txt"
# then Read _pytest_out.txt
```

**PG (db-marked) guard invocation pattern:**
```powershell
docker start promtech-cabinet-db-1 | Out-Null
$env:PYTHONPATH = "D:\Кодинг\Создание платформы по ОТ\backend"
$env:TEST_PG_ADMIN_URL = "postgresql://postgres:postgres@localhost:5432/postgres"
& "D:\Кодинг\Создание платформы по ОТ\.venv\Scripts\python.exe" -m pytest `
  backend/tests/test_orm_enum_pg_label_parity.py -v -m db `
  *> "D:\Кодинг\Создание платформы по ОТ\_pytest_out.txt"
# then Read _pytest_out.txt
```

> In the per-task commands below, `...python.exe` abbreviates `D:\Кодинг\Создание платформы по ОТ\.venv\Scripts\python.exe`, `..._pytest_out.txt` is a scratch file under the repo root, and `$env:PYTHONPATH` is always the backend dir (set as shown above). Always Read the redirect file for results — never rely on stdout.

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `backend/app/models/base.py` | `native_enum()` helper — single declaration site for the values_callable invariant | Modify |
| `backend/app/models/models.py` | 28 column type swaps + import | Modify |
| `backend/app/models/notifications.py` | 8 column type swaps + import | Modify |
| `backend/app/models/approval_workflow.py` | 4 column type swaps + import | Modify |
| `backend/app/models/document.py` | 3 column type swaps + import | Modify |
| `backend/app/models/finance.py` | 3 column type swaps + import | Modify |
| `backend/app/models/obligations.py` | 3 column type swaps + import | Modify |
| `backend/app/modules/workflow/models.py` | 3 column type swaps + import (module table; not in ALEMBIC_METADATA) | Modify |
| `backend/app/migrations/versions/20260602_iter49_enum_label_parity.py` | ADD VALUE backfill (4 types) + 8-heads merge | Create |
| `backend/tests/test_native_enum_helper.py` | Unit test for the helper | Create |
| `backend/tests/test_orm_enum_values_callable_parity.py` | Fast no-PG pin of the 52 | Create |
| `backend/tests/test_orm_enum_pg_label_parity.py` | Authoritative `@pytest.mark.db` label-subset guard + ORM-insert smoke | Create |
| `KNOWN_LIMITATIONS.md` | Document the pre-existing-UPPER-rows backfill caveat | Modify |

---

## Task 1: `native_enum()` helper

**Files:**
- Modify: `backend/app/models/base.py`
- Test: `backend/tests/test_native_enum_helper.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_native_enum_helper.py`:

```python
"""Unit test for the native_enum() helper: it must produce an Enum that binds
the member .value (lowercase/CamelCase), not the member NAME."""
from __future__ import annotations

import enum

from app.models.base import native_enum


class _Color(str, enum.Enum):
    RED = "red"
    DARK_BLUE = "dark_blue"


def test_native_enum_binds_values_not_names() -> None:
    t = native_enum(_Color, name="color")
    assert list(t.enums) == ["red", "dark_blue"]      # .value, not NAME
    assert t.name == "color"
    assert t.enum_class is _Color


def test_native_enum_derives_name_when_omitted() -> None:
    t = native_enum(_Color)
    # SQLAlchemy derives the type name from the enum class when name is omitted.
    assert list(t.enums) == ["red", "dark_blue"]
```

- [ ] **Step 2: Run test to verify it fails**

Run (fast pattern above, target this file). Expected: FAIL with `ImportError: cannot import name 'native_enum' from 'app.models.base'`.

- [ ] **Step 3: Implement the helper**

In `backend/app/models/base.py`, add `Enum` to the sqlalchemy import (line 6):

```python
from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
```

Add `"native_enum"` to `__all__` (line 11-16), then add after the imports (e.g. after line 16):

```python
def native_enum(enum_cls, *, name=None, **kw):
    """Native PG enum column type that persists the member ``.value`` rather than
    SQLAlchemy's default member NAME.

    Most ``pg_enum`` types in this project were created by migrations with
    ``.value`` labels (lowercase, or CamelCase for ``NotificationType``). Without
    ``values_callable`` SQLAlchemy binds the member NAME (UPPER) and PG rejects the
    INSERT with ``InvalidTextRepresentationError``. This is the canonical
    extraction of the inline precedent at ``document.py`` / ``models.py`` (the
    7 pre-existing ``values_callable`` columns). Pinned by
    ``backend/tests/test_orm_enum_pg_label_parity.py`` (authoritative, live PG) and
    ``backend/tests/test_orm_enum_values_callable_parity.py`` (fast, no PG).

    Only apply to Group-A columns (pg type created with ``.value`` labels). Do NOT
    apply to Group-B columns whose pg type was created with UPPER member NAMES — see
    the spec Appendix.
    """
    return Enum(enum_cls, name=name, values_callable=lambda e: [m.value for m in e], **kw)
```

- [ ] **Step 4: Run test to verify it passes**

Run the same target. Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/base.py backend/tests/test_native_enum_helper.py
git commit -m "feat(models): native_enum() helper binding enum .value for PG parity"
```

---

## Task 2: Write both guard tests (expected RED)

These define the target state. Both stay RED until the column edits (Tasks 3-8) and the migration (Task 9) land. Committing temporarily-red guards on this feature branch is intentional.

**Files:**
- Test: `backend/tests/test_orm_enum_values_callable_parity.py` (fast, no PG)
- Test: `backend/tests/test_orm_enum_pg_label_parity.py` (authoritative, PG)

- [ ] **Step 1: Write the fast no-PG pin**

Create `backend/tests/test_orm_enum_values_callable_parity.py`:

```python
"""Fast pin (no PG): the 52 known ORM↔pg_enum label-drift columns must bind .value.

Authoritative source is the @pytest.mark.db keystone guard
(test_orm_enum_pg_label_parity.py), which introspects live pg_enum labels. This
fast pin lists the exact 52 Group-A columns from the 2026-06-02 audit so the
normal (no-Docker) suite catches regressions and gives incremental feedback.

NOT a universal "every native enum binds .value" rule: 31 Group-B columns have pg
types created with UPPER member-NAME labels and correctly bind names — adding
values_callable there would break PG inserts (see spec Appendix)."""
from __future__ import annotations

from sqlalchemy import Enum as SAEnum

import app.db.base  # noqa: F401  triggers all model imports incl. app.modules.*
from app.db.session import SharedBase, TenantBase

# Complete table registry. NOTE: app.db.base.ALEMBIC_METADATA omits app.modules.*
# (it is snapshotted before those imports — see spec Appendix), so iterate the live
# SharedBase + TenantBase registries instead.
ALL_TABLES = {}
for _md in (SharedBase.metadata, TenantBase.metadata):
    ALL_TABLES.update(_md.tables)

# (table, column) — exactly the 52 Group-A defective columns (2026-06-02 full PG audit).
DEFECTIVE_COLUMNS = {
    # models.py (28)
    ("subscriptions", "status"), ("invoices", "status"), ("billing_events", "type"),
    ("user", "role"), ("user_role", "role"), ("training_session", "status"),
    ("ppeitem", "category"), ("package_profiles_v2", "status"),
    ("package_presets_v2", "source_type"), ("package_presets_v2", "status"),
    ("package_preset_items", "replace_mode"), ("package_preset_items", "output_format"),
    ("pack_runs", "source_type"), ("pack_runs", "status"), ("pack_run_items", "status"),
    ("pack_run_logs", "level"), ("package_runs", "status"),
    ("package_requirements", "type"), ("package_requirements", "status"),
    ("client_request_tickets", "status"), ("journal", "journal_type"),
    ("journalentry", "entry_type"), ("regulatory_inspection", "inspection_type"),
    ("attestation", "status"), ("inspection_prescription", "status"),
    ("approval_processes", "status"), ("approval_tasks", "status"),
    ("edo_envelopes", "status"),
    # notifications.py (8)
    ("notification_templates", "channel"), ("notification_templates", "type"),
    ("notifications", "channel"), ("notifications", "type"),
    ("notifications", "priority"), ("notifications", "status"),
    ("reminder_rules", "entity_type"), ("plan_tasks", "status"),
    # approval_workflow.py (4)
    ("approval_requests", "status"), ("signatures", "status"),
    ("edo_messages", "direction"), ("edo_status_history", "status"),
    # document.py (3)
    ("document", "status"), ("document_batch_run", "status"),
    ("document_batch_item", "status"),
    # finance.py (3)
    ("contract", "status"), ("order", "status"), ("invoice", "status"),
    # obligations.py (3)
    ("task", "status"), ("task", "priority"), ("task", "reminder_channel"),
    # app/modules/workflow/models.py (3)
    ("workflow_definition_versions", "status"), ("workflow_instances", "status"),
    ("workflow_tasks", "status"),
}


def test_exactly_52_columns_pinned() -> None:
    assert len(DEFECTIVE_COLUMNS) == 52


def test_defective_columns_bind_enum_values_not_names() -> None:
    offenders = []
    for table_name, col_name in sorted(DEFECTIVE_COLUMNS):
        col = ALL_TABLES[table_name].columns[col_name]
        t = col.type
        assert isinstance(t, SAEnum) and t.enum_class is not None, f"{table_name}.{col_name} not a native enum"
        if list(t.enums) != [m.value for m in t.enum_class]:
            offenders.append(
                f"{table_name}.{col_name}: binds {list(t.enums)} not {[m.value for m in t.enum_class]}"
            )
    assert not offenders, "columns still bind member NAMES (apply native_enum):\n" + "\n".join(offenders)
```

- [ ] **Step 2: Write the authoritative PG guard**

Create `backend/tests/test_orm_enum_pg_label_parity.py`:

```python
"""DB guard: every native pg-enum ORM column must bind strings ⊆ live pg_enum labels.

The SQLite suite cannot catch ORM↔pg_enum label drift (Enum→VARCHAR accepts any
string). This guard upgrades a throwaway PG to heads, introspects pg_enum, and
asserts that for every native-enum ORM column the strings SQLAlchemy will bind
(col.type.enums — which reflects values_callable) are a subset of the live labels.
RED before the fix (52 defective columns); GREEN after.

Also smoke-tests a real ORM insert of a previously-defective entity (Notification,
exercising the newly-added 'webhook' + 'ApprovalDeadline' labels) and raw casts of
the other newly-added labels.

Skips unless TEST_PG_ADMIN_URL points at a PG superuser/owner maintenance DB (e.g.
postgresql://postgres:postgres@localhost:5432/postgres). NEVER touches `cabinet`."""
from __future__ import annotations

import asyncio
import os
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")
REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "app" / "migrations" / "alembic.ini"
SCRIPT_LOCATION = REPO_ROOT / "backend" / "app" / "migrations"


def _sync_base() -> str:
    return ADMIN_URL.rsplit("/", 1)[0]


def _async_url(dbname: str) -> str:
    base = _sync_base().replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{dbname}"


async def _exec(sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


async def _labels(dbname: str) -> dict[str, set[str]]:
    import asyncpg

    conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
    try:
        rows = await conn.fetch(
            "SELECT t.typname, e.enumlabel FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid"
        )
    finally:
        await conn.close()
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        out[r["typname"]].add(r["enumlabel"])
    return out


def _upgrade(dbname: str) -> None:
    from alembic import command
    from alembic.config import Config

    os.environ["DATABASE_URL"] = _async_url(dbname)
    from app.core.config import get_settings

    get_settings.cache_clear()
    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    command.upgrade(cfg, "heads")


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pg-enum label guard")
def test_orm_enum_bound_values_subset_of_pg_labels() -> None:
    from sqlalchemy import Enum as SAEnum

    dbname = f"enum_parity_{uuid.uuid4().hex[:12]}"
    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        pg = asyncio.run(_labels(dbname))

        import app.db.base  # noqa: F401  triggers all model imports incl. app.modules.*
        from app.db.session import SharedBase, TenantBase

        all_tables = {}
        for md in (SharedBase.metadata, TenantBase.metadata):
            all_tables.update(md.tables)

        offenders = []
        for table in all_tables.values():
            for col in table.columns:
                t = col.type
                if not isinstance(t, SAEnum) or not getattr(t, "native_enum", False):
                    continue
                typ = (t.name or "").lower()
                if typ not in pg:
                    continue
                bad = set(t.enums) - pg[typ]
                if bad:
                    offenders.append(
                        f"{table.name}.{col.name} (type {typ}) would bind {sorted(bad)} ∉ {sorted(pg[typ])}"
                    )
        assert not offenders, "ORM↔pg_enum label drift:\n" + "\n".join(offenders)
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pg-enum insert smoke")
def test_real_orm_insert_of_previously_defective_entity() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

    from app.models.models import Tenant
    from app.models.notifications import (
        Notification,
        NotificationChannel,
        NotificationPriority,
        NotificationStatus,
        NotificationType,
    )

    dbname = f"enum_insert_{uuid.uuid4().hex[:12]}"
    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))

    async def _run() -> None:
        engine = create_async_engine(_async_url(dbname))
        try:
            async with AsyncSession(engine) as session:
                tenant = Tenant(slug=f"t-{uuid.uuid4().hex[:8]}", name="Smoke", contact_email="s@e.t")
                session.add(tenant)
                await session.flush()
                note = Notification(
                    tenant_id=tenant.id,
                    user_id="u-1",
                    channel=NotificationChannel.WEBHOOK,       # 'webhook' — newly added label
                    type=NotificationType.APPROVAL_DEADLINE,    # 'ApprovalDeadline' — newly added label
                    title="t",
                    body="b",
                    priority=NotificationPriority.HIGH,
                    status=NotificationStatus.QUEUED,
                    dedup_key=f"d-{uuid.uuid4().hex[:8]}",
                    scheduled_at=datetime(2026, 6, 2, tzinfo=timezone.utc),
                )
                session.add(note)
                await session.commit()
                got = await session.get(Notification, note.id)
                assert got is not None
                assert got.channel is NotificationChannel.WEBHOOK
                assert got.type is NotificationType.APPROVAL_DEADLINE
        finally:
            await engine.dispose()

    try:
        os.environ["DATABASE_URL"] = _async_url(dbname)
        from app.core.config import get_settings

        get_settings.cache_clear()
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
```

- [ ] **Step 3: Run the fast pin to confirm it fails as expected**

Run `backend/tests/test_orm_enum_values_callable_parity.py` (fast pattern). Expected: `test_exactly_52_columns_pinned` PASS; `test_defective_columns_bind_enum_values_not_names` FAIL listing 52 columns that "still bind member NAMES".

- [ ] **Step 4: Run the PG guard to confirm it fails as expected**

Run `backend/tests/test_orm_enum_pg_label_parity.py` (PG pattern). Expected: `test_orm_enum_bound_values_subset_of_pg_labels` FAIL with "ORM↔pg_enum label drift:" listing 52 columns; the insert smoke FAILS (webhook/ApprovalDeadline not yet valid labels).

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_orm_enum_values_callable_parity.py backend/tests/test_orm_enum_pg_label_parity.py
git commit -m "test(models): RED guards for ORM<->pg_enum label parity (fast pin + live-PG)"
```

---

## Task 3: Apply `native_enum` in `approval_workflow.py` (4 columns)

**Files:**
- Modify: `backend/app/models/approval_workflow.py`

- [ ] **Step 1: Add the import**

Change line 21 from:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel
```
to:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum
```

- [ ] **Step 2: Swap the 4 defective column types** (leave `ApprovalRouteAppliesTo`, `ApprovalRouteStatus`, `SignatureType` — those are Group-B/VARCHAR, untouched)

| Line | Replace | With |
|---|---|---|
| 151 | `Enum(ApprovalRequestStatus)` | `native_enum(ApprovalRequestStatus)` |
| 188 | `Enum(SignatureStatus)` | `native_enum(SignatureStatus)` |
| 203 | `Enum(EdoDirection)` | `native_enum(EdoDirection)` |
| 240 | `Enum(EdoStatus)` | `native_enum(EdoStatus)` |

(Each `Enum(...)` string above is unique in this file — `SignatureStatus` ≠ `SignatureType`.)

- [ ] **Step 3: Run the fast pin to confirm 4 fewer offenders**

Run `backend/tests/test_orm_enum_values_callable_parity.py`. Expected: still FAIL, but the 4 `approval_workflow` columns (approval_requests.status, signatures.status, edo_messages.direction, edo_status_history.status) no longer listed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/approval_workflow.py
git commit -m "fix(models): native_enum for approval_workflow enum cols (PG parity)"
```

---

## Task 4: Apply `native_enum` in `document.py` (3 columns)

**Files:**
- Modify: `backend/app/models/document.py`

- [ ] **Step 1: Add the import**

Change line 14 from:
```python
from app.models.base import TenantBaseModel
```
to:
```python
from app.models.base import TenantBaseModel, native_enum
```

- [ ] **Step 2: Swap the 3 defective column types** (leave `DocumentVersionStatus` @163 — already has values_callable — and `DocumentJobStatus` @287 — Group-B)

| Line | Replace | With |
|---|---|---|
| 65 | `Enum(DocumentStatus, name="documentstatus")` | `native_enum(DocumentStatus, name="documentstatus")` |
| 364 | `Enum(DocumentBatchStatus, name="documentbatchstatus")` | `native_enum(DocumentBatchStatus, name="documentbatchstatus")` |
| 416 | `Enum(DocumentBatchItemStatus, name="documentbatchitemstatus")` | `native_enum(DocumentBatchItemStatus, name="documentbatchitemstatus")` |

- [ ] **Step 3: Run the fast pin**

Run the fast test. Expected: document.status, document_batch_run.status, document_batch_item.status no longer listed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/document.py
git commit -m "fix(models): native_enum for document enum cols (PG parity)"
```

---

## Task 5: Apply `native_enum` in `finance.py` (3 columns)

**Files:**
- Modify: `backend/app/models/finance.py`

- [ ] **Step 1: Add the import**

Change line 11 from:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel
```
to:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum
```

- [ ] **Step 2: Swap the 3 column types**

| Line | Replace | With |
|---|---|---|
| 69 | `Enum(ContractStatus, name="contractstatus")` | `native_enum(ContractStatus, name="contractstatus")` |
| 103 | `Enum(OrderStatus, name="orderstatus")` | `native_enum(OrderStatus, name="orderstatus")` |
| 136 | `Enum(InvoiceStatus, name="invoicestatus")` | `native_enum(InvoiceStatus, name="invoicestatus")` |

- [ ] **Step 3: Run the fast pin** — contract.status, order.status, invoice.status no longer listed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/finance.py
git commit -m "fix(models): native_enum for finance enum cols (PG parity)"
```

---

## Task 6: Apply `native_enum` in `obligations.py` (3 columns)

**Files:**
- Modify: `backend/app/models/obligations.py`

- [ ] **Step 1: Add the import**

Change line 12 from:
```python
from app.models.base import TenantBaseModel
```
to:
```python
from app.models.base import TenantBaseModel, native_enum
```

- [ ] **Step 2: Swap the 3 column types**

| Line | Replace | With |
|---|---|---|
| 50 | `Enum(TaskStatus, name="taskstatus")` | `native_enum(TaskStatus, name="taskstatus")` |
| 59 | `Enum(TaskPriority, name="taskpriority")` | `native_enum(TaskPriority, name="taskpriority")` |
| 65 | `Enum(TaskReminderChannel, name="taskreminderchannel")` | `native_enum(TaskReminderChannel, name="taskreminderchannel")` |

- [ ] **Step 3: Run the fast pin** — task.status, task.priority, task.reminder_channel no longer listed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/obligations.py
git commit -m "fix(models): native_enum for obligations task enum cols (PG parity)"
```

---

## Task 7: Apply `native_enum` in `notifications.py` (8 columns)

**Files:**
- Modify: `backend/app/models/notifications.py`

- [ ] **Step 1: Add the import**

Change line 11 from:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel
```
to:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum
```

- [ ] **Step 2: Swap all 8 column types** (each has a distinct `name=`, so each string is unique)

| Line | Replace | With |
|---|---|---|
| 69 | `Enum(NotificationChannel, name="notificationtemplatechannel")` | `native_enum(NotificationChannel, name="notificationtemplatechannel")` |
| 70 | `Enum(NotificationType, name="notificationtemplatetype")` | `native_enum(NotificationType, name="notificationtemplatetype")` |
| 104 | `Enum(NotificationChannel, name="notificationchannel")` | `native_enum(NotificationChannel, name="notificationchannel")` |
| 105 | `Enum(NotificationType, name="notificationtype")` | `native_enum(NotificationType, name="notificationtype")` |
| 109 | `Enum(NotificationPriority, name="notificationpriority")` | `native_enum(NotificationPriority, name="notificationpriority")` |
| 110 | `Enum(NotificationStatus, name="notificationstatus")` | `native_enum(NotificationStatus, name="notificationstatus")` |
| 146 | `Enum(ReminderEntityType, name="reminderentitytype")` | `native_enum(ReminderEntityType, name="reminderentitytype")` |
| 171 | `Enum(PlanTaskStatus, name="plantaskstatus_v2")` | `native_enum(PlanTaskStatus, name="plantaskstatus_v2")` |

- [ ] **Step 3: Run the fast pin** — the 8 notifications columns no longer listed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/notifications.py
git commit -m "fix(models): native_enum for notifications enum cols (PG parity)"
```

---

## Task 8: Apply `native_enum` in `models.py` (28 columns)

**Files:**
- Modify: `backend/app/models/models.py`

- [ ] **Step 1: Add the import**

`models.py` already has a multi-line `from app.models.base import (` at line 48. Add `native_enum,` to that import list (alphabetical or appended — match the file's style).

- [ ] **Step 2: Swap the 28 defective column types.** Use `replace_all` ONLY for `Enum(RoleEnum)` and `Enum(JournalType)` (each appears twice — both are targets); all others are unique single occurrences.

`replace_all` pair (2 lines each):

| Replace (all) | With |
|---|---|
| `Enum(RoleEnum)` | `native_enum(RoleEnum)` |
| `Enum(JournalType)` | `native_enum(JournalType)` |

Single replacements:

| Line | Replace | With |
|---|---|---|
| 318 | `Enum(BillingSubscriptionStatus)` | `native_enum(BillingSubscriptionStatus)` |
| 361 | `Enum(BillingInvoiceStatus)` | `native_enum(BillingInvoiceStatus)` |
| 382 | `Enum(BillingEventType)` | `native_enum(BillingEventType)` |
| 912 | `Enum(TrainingSessionStatus)` | `native_enum(TrainingSessionStatus)` |
| 1321 | `Enum(PPEItemCategory)` | `native_enum(PPEItemCategory)` |
| 1541 | `Enum(PackageEntityStatus, name="package_entity_status")` | `native_enum(PackageEntityStatus, name="package_entity_status")` |
| 1562 | `Enum(PackageSourceType, name="package_source_type")` | `native_enum(PackageSourceType, name="package_source_type")` |
| 1567 | `Enum(PackageEntityStatus, name="package_preset_status")` | `native_enum(PackageEntityStatus, name="package_preset_status")` |
| 1590 | `Enum(ReplaceMode, name="replace_mode")` | `native_enum(ReplaceMode, name="replace_mode")` |
| 1594 | `Enum(OutputFormat, name="package_output_format")` | `native_enum(OutputFormat, name="package_output_format")` |
| 1616 | `Enum(PackageSourceType, name="pack_run_source_type")` | `native_enum(PackageSourceType, name="pack_run_source_type")` |
| 1620 | `Enum(PackRunLifecycleStatus, name="pack_run_lifecycle_status")` | `native_enum(PackRunLifecycleStatus, name="pack_run_lifecycle_status")` |
| 1648 | `Enum(PackRunItemStatus, name="pack_run_item_status")` | `native_enum(PackRunItemStatus, name="pack_run_item_status")` |
| 1666 | `Enum(PackLogLevel, name="pack_log_level")` | `native_enum(PackLogLevel, name="pack_log_level")` |
| 1867 | `Enum(PackageRunStatus)` | `native_enum(PackageRunStatus)` |
| 1890 | `Enum(PackageRequirementType)` | `native_enum(PackageRequirementType)` |
| 1893 | `Enum(PackageRequirementStatus)` | `native_enum(PackageRequirementStatus)` |
| 1919 | `Enum(ClientRequestTicketStatus)` | `native_enum(ClientRequestTicketStatus)` |
| 2439 | `Enum(InspectionType, name="inspectiontype")` | `native_enum(InspectionType, name="inspectiontype")` |
| 2520 | `Enum(AttestationStatus, name="attestationstatus")` | `native_enum(AttestationStatus, name="attestationstatus")` |
| 2560 | `Enum(PrescriptionStatus, name="prescriptionstatus")` | `native_enum(PrescriptionStatus, name="prescriptionstatus")` |
| 2631 | `Enum(ApprovalProcessStatus)` | `native_enum(ApprovalProcessStatus)` |
| 2650 | `Enum(ApprovalTaskStatus)` | `native_enum(ApprovalTaskStatus)` |
| 2814 | `Enum(EdoEnvelopeStatus)` | `native_enum(EdoEnvelopeStatus)` |

**DO NOT TOUCH** (Group-B / VARCHAR / already-correct): `Enum("customer",…)` @218, the multi-line `Enum(` @745 (employment_status), `Enum(TrainingStatus)` @832, `Enum(PermitStatus)` @1275, `Enum(PPEIssueStatus)` @1352, `Enum(TemplateStatus)` @1405, `Enum(TemplateVersionStatus)` @1436, multi-line `Enum(` @1721/1733 (document_pack), `Enum(PipelineRunStatus)` @1788, `Enum(NPAStatus)` @2069, multi-line `Enum(` @2091 (npabinding), `Enum(PlanTaskStatus)` @2274 (plantask, Group-B — note this is `plantaskstatus`, distinct from notifications' `plantaskstatus_v2`), the incident.* enums @2312-2403, `Enum(InspectionStatus, name="regulatoryinspectionstatus")` @2453, `Enum(EquipmentStatus)` @2596, the approval route/instance enums @2683/2705/2727, `Enum(OutboxStatus)` @2831.

- [ ] **Step 3: Run the fast pin — only the 3 workflow columns should remain**

Run `backend/tests/test_orm_enum_values_callable_parity.py`. Expected: `test_defective_columns_bind_enum_values_not_names` still FAILS, listing exactly the 3 `app.modules.workflow` columns (workflow_definition_versions.status, workflow_instances.status, workflow_tasks.status). All `app.models.*` columns are now fixed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/models.py
git commit -m "fix(models): native_enum for 28 models.py enum cols (PG parity)"
```

---

## Task 8b: Apply `native_enum` in `app/modules/workflow/models.py` (3 columns)

These module tables are **not** in `ALEMBIC_METADATA` (snapshotted before the module imports) but **are** created on PG by the workflow migration, so they have the same drift. Their pg types already hold the lowercase labels — no ADD VALUE needed.

**Files:**
- Modify: `backend/app/modules/workflow/models.py`

- [ ] **Step 1: Add the import**

Change line 12 from:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel
```
to:
```python
from app.models.base import SoftDeleteMixin, TenantBaseModel, native_enum
```

- [ ] **Step 2: Swap the 3 column types**

| Line | Replace | With |
|---|---|---|
| 60 | `Enum(WorkflowDefinitionStatus, name="workflowdefinitionstatus")` | `native_enum(WorkflowDefinitionStatus, name="workflowdefinitionstatus")` |
| 79 | `Enum(WorkflowInstanceStatus, name="workflowinstancestatus")` | `native_enum(WorkflowInstanceStatus, name="workflowinstancestatus")` |
| 100 | `Enum(WorkflowTaskStatus, name="workflowtaskstatus")` | `native_enum(WorkflowTaskStatus, name="workflowtaskstatus")` |

- [ ] **Step 3: Run the fast pin — now fully GREEN (all 52 fixed)**

Run `backend/tests/test_orm_enum_values_callable_parity.py`. Expected: PASS (2 passed) — both `test_exactly_52_columns_pinned` and `test_defective_columns_bind_enum_values_not_names` green.

- [ ] **Step 4: Sanity-check imports**

```powershell
& "...python.exe" -m pytest backend/tests/test_native_enum_helper.py backend/tests/test_orm_enum_values_callable_parity.py -v *> "..._pytest_out.txt"
```
Expected: all PASS (confirms no import typo broke model loading).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/workflow/models.py
git commit -m "fix(models): native_enum for workflow module enum cols (PG parity)"
```

---

## Task 9: ADD VALUE migration (+ merge the 8 heads)

**Files:**
- Create: `backend/app/migrations/versions/20260602_iter49_enum_label_parity.py`

- [ ] **Step 1: Verify the current heads still match the plan**

```powershell
$env:PYTHONPATH = "D:\Кодинг\Создание платформы по ОТ\backend"
& "...python.exe" -c "from alembic.config import Config; from alembic.script import ScriptDirectory; from pathlib import Path; r=Path(r'D:\Кодинг\Создание платформы по ОТ'); c=Config(str(r/'backend/app/migrations/alembic.ini')); c.set_main_option('script_location', str(r/'backend/app/migrations')); print(sorted(ScriptDirectory.from_config(c).get_heads()))"
```
Expected 8 heads: `20260529_iter35_riskmap_company`, `20260529_iter40_tc_legacy_cols`, `20260529_iter41_journalentry_concept`, `20260529_iter42_incident_family`, `20260529_iter43_incident_status_enum`, `20260529_iter46_approval_decisions_cols`, `20260529_iter47_file_business_cols`, `20260530_wa03_prescription_lifecycle`. **If different, use the actual output as the `down_revision` tuple** in Step 2.

- [ ] **Step 2: Write the migration**

Create `backend/app/migrations/versions/20260602_iter49_enum_label_parity.py`:

```python
"""iter-49: ORM<->pg_enum label parity — backfill missing .value labels.

The ORM now binds enum member .value (via native_enum/values_callable) for 52
columns whose pg_enum types were created with .value labels. Four of those types
are missing some .value labels; add them so ORM inserts succeed:

  documentstatus       += archived, draft, review, signed  (had only UPPER variants)
  notificationchannel  += webhook
  notificationtype     += 11 newer members (notifications.type; the *template* type
                          notificationtemplatetype is already complete)
  roleenum             += 9 lowercase roles (had UPPER variants / were absent)

ADD VALUE IF NOT EXISTS is idempotent and retry-safe under the env.py AUTOCOMMIT +
transaction_per_migration config (the labels are NOT used as a server_default in
this migration, so no UnsafeNewEnumValueUsageError). SQLite is a no-op (Enum->VARCHAR).

Heads-merge: at authoring time the tree had 8 divergent heads (iter43 docstring
noted the pending merge). This revision's down_revision is the tuple of all 8, so
it doubles as the merge -> single head.

Downgrade: no-op. PG has no DROP VALUE; the added labels are additive and harmless.

Pre-existing data caveat (out of scope, documented in KNOWN_LIMITATIONS.md): rows
written before this change under the old name-binding behavior may hold UPPER
strings (role, document.status) and would need a one-time UPDATE backfill. Fresh-PG
(the canonical target) is unaffected.
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260602_iter49_enum_label_parity"
down_revision: str | Sequence[str] | None = (
    "20260529_iter35_riskmap_company",
    "20260529_iter40_tc_legacy_cols",
    "20260529_iter41_journalentry_concept",
    "20260529_iter42_incident_family",
    "20260529_iter43_incident_status_enum",
    "20260529_iter46_approval_decisions_cols",
    "20260529_iter47_file_business_cols",
    "20260530_wa03_prescription_lifecycle",
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# pg type -> missing labels (authoritative: 2026-06-02 fresh-PG audit).
ADD_VALUES: dict[str, tuple[str, ...]] = {
    "documentstatus": ("archived", "draft", "review", "signed"),
    "notificationchannel": ("webhook",),
    "notificationtype": (
        "ApprovalDeadline", "BillingLimitWarning", "EdoStatusChanged",
        "IncidentCreated", "InspectionCreated", "IntegrationError",
        "MedicalOverdue", "PPEOverdue", "PackageRunCompleted",
        "PackageRunFailed", "PrescriptionOverdue",
    ),
    "roleenum": (
        "auditor_ro", "clerk", "client", "executor", "inspector_contractor",
        "manager", "ot_head", "student", "teacher",
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for type_name, values in ADD_VALUES.items():
        for value in values:
            op.execute(f"ALTER TYPE {type_name} ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # No-op: PG has no DROP VALUE; added labels are additive and harmless.
    pass
```

- [ ] **Step 3: Confirm the tree now has a single head**

Re-run the heads command from Step 1. Expected: exactly `['20260602_iter49_enum_label_parity']`.

- [ ] **Step 4: Run the PG guard — both tests now GREEN**

Run `backend/tests/test_orm_enum_pg_label_parity.py` (PG pattern). Expected: `test_orm_enum_bound_values_subset_of_pg_labels` PASS (no drift) and `test_real_orm_insert_of_previously_defective_entity` PASS (webhook + ApprovalDeadline insert round-trips).

- [ ] **Step 5: Commit**

```bash
git add backend/app/migrations/versions/20260602_iter49_enum_label_parity.py
git commit -m "fix(migrations): iter49 ADD VALUE enum-label backfill + merge 8 heads (PG parity)"
```

---

## Task 10: Run the full existing suite; fix UPPER stored-string assertions

`values_callable` changes the SQLite-stored string from the member NAME (UPPER) to `.value` (lowercase/CamelCase) for the 52 columns. Most assertions use `Member` or `Member.value` and are unaffected (`str`-enums compare equal to their value), but some tests may assert a raw UPPER stored string.

**Files:**
- Modify: any test that fails per Step 2 (unknown until run).

- [ ] **Step 1: Run the app-free / unit slice of the suite**

```powershell
$env:PYTHONPATH = "D:\Кодинг\Создание платформы по ОТ\backend"
& "...python.exe" -m pytest backend/tests/unit -q *> "..._pytest_out.txt"
# then also run any enum/model-focused suites:
& "...python.exe" -m pytest backend/tests -q -k "enum or status or role or notification or journal or package or pack_run or attestation or signature or edo or billing or document or task" *> "..._pytest_out2.txt"
```
Read both output files.

- [ ] **Step 2: For each failure asserting an UPPER stored string, update it**

Pattern: a failure like `assert "PENDING" == "pending"` or a DB-read expecting UPPER. Change the expectation to the `.value` (lowercase/CamelCase) or compare against the enum member. **Do not** revert any `native_enum` change. Record each touched test file.

- [ ] **Step 3: Re-run until green**

Re-run the same selections. Expected: PASS (or pre-existing unrelated failures only — note them, do not fix out-of-scope).

- [ ] **Step 4: Commit (only if any test files changed)**

```bash
git add backend/tests/<changed test files>
git commit -m "test: update enum stored-string assertions to .value after native_enum"
```

---

## Task 11: Document the pre-existing-rows caveat

**Files:**
- Modify: `KNOWN_LIMITATIONS.md`

- [ ] **Step 1: Add a caveat entry**

Append a short subsection to `KNOWN_LIMITATIONS.md` (match the file's existing heading style):

```markdown
### ORM enum-label parity (iter-49, 2026-06-02): pre-existing UPPER rows need backfill

52 native-enum ORM columns now bind the member `.value` (lowercase/CamelCase) via
`native_enum`/`values_callable`, matching their `pg_enum` labels (iter-49 also adds
the few missing labels). Fresh-PG is fully correct. **Caveat:** any DB written
*before* iter-49 may hold UPPER member-NAME strings in these columns (notably
`user.role`, `user_role.role`, `document.status`). Those rows need a one-time data
backfill (`UPDATE … SET col = lower(col)` / explicit value mapping) to remain
queryable by the ORM after the switch. The pre-release `cabinet` DB is intentionally
untouched; perform the backfill before promoting any pre-iter-49 database.
```

- [ ] **Step 2: Commit**

```bash
git add KNOWN_LIMITATIONS.md
git commit -m "docs: note pre-existing UPPER enum rows need backfill (iter49 parity)"
```

---

## Task 12: Final verification

- [ ] **Step 1: Fast suite green**

Run `backend/tests/test_native_enum_helper.py` + `backend/tests/test_orm_enum_values_callable_parity.py`. Expected: all PASS.

- [ ] **Step 2: PG guards green**

Run `backend/tests/test_orm_enum_pg_label_parity.py` (PG pattern) AND the pre-existing `backend/tests/test_alembic_postgres_upgrade.py` (PG pattern). Expected: all PASS (the latter confirms the heads-merge didn't break `upgrade heads`).

- [ ] **Step 3: Confirm throwaway DBs cleaned, `cabinet` untouched**

```powershell
# List DBs: confirm `cabinet` is present and there are no enum_parity_* / enum_insert_*
# leftovers (the guards drop their throwaway DBs in a finally block).
docker exec promtech-cabinet-db-1 psql -U postgres -c "SELECT datname FROM pg_database WHERE datname LIKE 'enum_%' OR datname = 'cabinet';"
```
Expected: `cabinet` present; no `enum_parity_*` / `enum_insert_*` leftovers (the guards drop them in `finally`).

- [ ] **Step 4: Review the diff**

```bash
git log --oneline main..HEAD
git diff --stat main..HEAD
```
Expected: helper + 7 model files (6 in `models/` + the workflow module) + 1 migration + 3 test files + KNOWN_LIMITATIONS (+ any Task 10 test fixes), all on `fix/orm-enum-pg-label-parity`.

- [ ] **Step 5: Hand off to requesting-code-review** (per the development workflow) before opening the PR.

---

## Notes for the executor

- **One logical step per message** when editing→testing→committing — concurrent tool calls race on this machine (`[[py313_win_pytest_invocation]]`). Read pytest output from the redirect file, not stdout.
- The fast pin (Task 2) is the incremental feedback loop for Tasks 3-8; the PG guard (Task 2/9) is authoritative.
- If `git diff main..HEAD` shows any Group-B column (e.g. `incident.severity`, `equipment.status`) changed to `native_enum`, that is a **bug** — revert it; those bind member NAMES correctly.
- Do not linearize/rewrite the 8 pre-existing heads other than via the iter-49 merge.
