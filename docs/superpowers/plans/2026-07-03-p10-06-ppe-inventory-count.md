# P10-06 СИЗ склад — «Инвентаризация» Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-phase inventory-count (stocktake) workflow to the PPE warehouse — physical counts per batch reconciled into `adjustment` stock movements — closing the honest-balance loop.

**Architecture:** New `ppe_inventory_count` (header, `draft→applied/cancelled`) + `ppe_inventory_count_line` (per-batch snapshot) tables (additive migration `wa06`). A new service module `app.modules.ppe.inventory` seeds a count from live batches, records physical counts, and on `apply` emits `adjustment` movements **through the existing `record_movement` chokepoint** (extended additively with `ref_type`/`ref_id`) — the module never mutates `batch.quantity` directly. Six routes under `/api/v1/ppe/stock/inventory/*` behind the `warehouse` flag; one new frontend section on `WarehousePage`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy async / Alembic / pytest-asyncio; React 18 / Vite / TypeScript / vitest.

---

## Conventions for this plan

- **Backend test runner (Windows worktree — no `.venv`, `python` is a broken Store stub):** run each test in **foreground PowerShell** with the global interpreter:
  `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest <path> -q`
  `pythonpath` is set in `pyproject.toml`, so no manual `PYTHONPATH`. Local Python is 3.13 (repo canon 3.12.12) — note the mismatch, don't block. Steps below write `pytest <path>` as shorthand for this command.
- **The test DB is built via `metadata.create_all`** (per `tests/conftest.py`), so new tables exist in tests as soon as the ORM models (Task 1) are defined — service/API tests do **not** depend on the Alembic migration. The migration (Task 2) is validated only by the **PG16 gate** (`scripts/ci/local_gate.py --db-only`), not local pytest.
- **Frontend gates:** `npm --prefix frontend run typecheck`, `npm --prefix frontend run test`, `npm --prefix frontend run build`.
- **Commits:** `feat(p10-06): ...`, **no `Co-Authored-By` trailer** in subagent commits (the main session sets attribution). Commit after each task.
- **The `warehouse` flag defaults ON** with no `FeatureEnablement` row; seed a row only to force it OFF.

## File Structure

**Backend — create:**
- `backend/app/modules/ppe/inventory.py` — inventory-count workflow service (seed / set-counts / detail / list / apply / cancel). One responsibility: the stocktake lifecycle over the ledger.
- `backend/app/migrations/versions/20260703_wa06_ppe_inventory_count.py` — additive two-table migration.
- `backend/tests/test_ppe_inventory_count_model.py` — ORM-shape introspection test.
- `backend/tests/test_wa06_ppe_inventory_count_migration.py` — static migration-source test.
- `tests/api/test_ppe_inventory_count_service.py` — service/DB tests.
- `tests/api/test_ppe_inventory_count_api.py` — HTTP API tests.

**Backend — modify:**
- `backend/app/models/ppe.py` — add `PPEInventoryCount` + `PPEInventoryCountLine`.
- `backend/app/models/models.py` — extend the `from app.models.ppe import (...)` re-export + `__all__`.
- `backend/app/modules/ppe/stock.py` — additive `ref_type`/`ref_id` on `record_movement`.
- `backend/app/schemas/ppe.py` — inventory-count schemas.
- `backend/app/api/routes/ppe.py` — six inventory routes + imports.

**Frontend — modify:**
- `frontend/src/api/warehouse.ts` — DTOs + `warehouseApi` methods.
- `frontend/src/pages/warehouse/WarehousePage.tsx` — «Инвентаризация» section.
- `frontend/src/__tests__/WarehousePage.test.tsx` — vitest for the section.

**Docs — modify (Task 13):** `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, `CHANGELOG.md`, `docs/stabilization/openapi_routes_baseline.json`, `AI_IMPLEMENTATION_REPORT.md`.

---

### Task 1: ORM models (`PPEInventoryCount` + `PPEInventoryCountLine`)

**Files:**
- Modify: `backend/app/models/ppe.py` (append after `PPEStockMovement`, ~line 191)
- Modify: `backend/app/models/models.py` (re-export block ~line 206 + `__all__` ~line 591)
- Test: `backend/tests/test_ppe_inventory_count_model.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_ppe_inventory_count_model.py`:

```python
"""Pin: PPEInventoryCount(+Line) ORM shape (P10-06 inventory count)."""

from __future__ import annotations


def test_inventory_count_header_table_and_columns():
    from app.models.ppe import PPEInventoryCount

    assert PPEInventoryCount.__tablename__ == "ppe_inventory_count"
    cols = set(PPEInventoryCount.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "status",
        "scope_item_id",
        "scope_location",
        "note",
        "applied_at",
        "deleted_at",
        "version",
    } <= cols


def test_inventory_count_line_table_and_columns():
    from app.models.ppe import PPEInventoryCountLine

    assert PPEInventoryCountLine.__tablename__ == "ppe_inventory_count_line"
    cols = set(PPEInventoryCountLine.__table__.columns.keys())
    assert {
        "count_id",
        "item_id",
        "batch_id",
        "system_qty",
        "counted_qty",
        "adjustment_movement_id",
    } <= cols
    assert "deleted_at" not in cols  # line has no SoftDeleteMixin
    assert PPEInventoryCountLine.__table__.columns["counted_qty"].nullable is True
    assert PPEInventoryCountLine.__table__.columns["system_qty"].nullable is False


def test_inventory_count_reexported_from_models():
    from app.models.models import PPEInventoryCount, PPEInventoryCountLine  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_ppe_inventory_count_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'PPEInventoryCount' from 'app.models.ppe'`.

- [ ] **Step 3: Add the models**

In `backend/app/models/ppe.py`, append after the `PPEStockMovement` class (which ends near line 191, after its `__table_args__`). All needed imports (`Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint`, `Mapped, mapped_column, relationship`, `SoftDeleteMixin, TenantBaseModel`) are already imported at the top of the file:

```python
class PPEInventoryCount(TenantBaseModel, SoftDeleteMixin):
    """Stocktake session header (P10-06). Two-phase: ``draft`` → ``applied`` /
    ``cancelled``. ``apply`` emits ``adjustment`` movements via the ledger service —
    this table never mutates ``batch.quantity`` directly. ``status`` is VARCHAR, not
    a PG enum (enum-parity convention)."""

    __tablename__ = "ppe_inventory_count"

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")
    scope_item_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="SET NULL"), nullable=True
    )
    scope_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lines: Mapped[list["PPEInventoryCountLine"]] = relationship(
        "PPEInventoryCountLine", backref="count", cascade="all, delete-orphan"
    )


class PPEInventoryCountLine(TenantBaseModel):
    """One row per stock batch snapshotted into a count. ``counted_qty`` is nullable:
    ``None`` = not counted (skipped at apply); ``0`` = counted-zero (write-off).
    ``adjustment_movement_id`` is a plain string ref (no FK) so the append-only
    journal survives a hard-delete — same convention as ``PPEStockMovement.ref_id``."""

    __tablename__ = "ppe_inventory_count_line"

    count_id: Mapped[str] = mapped_column(
        ForeignKey("ppe_inventory_count.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[str] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[str] = mapped_column(
        ForeignKey("ppe_stock_batch.id", ondelete="CASCADE"), nullable=False
    )
    system_qty: Mapped[int] = mapped_column(Integer, nullable=False)
    counted_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adjustment_movement_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_ppe_inventory_count_line_count", "tenant_id", "count_id"),
        Index("ix_ppe_inventory_count_line_batch", "tenant_id", "batch_id"),
        UniqueConstraint(
            "tenant_id", "count_id", "batch_id", name="uq_ppe_inv_count_line_batch"
        ),
    )
```

- [ ] **Step 4: Extend the `app.models.models` re-export**

In `backend/app/models/models.py`, the block at line 206 is `from app.models.ppe import (`. Add the two new names (keep alphabetical grouping near the other `PPE*` entries):

```python
from app.models.ppe import (
    ...
    PPEInventoryCount,
    PPEInventoryCountLine,
    ...
    PPEStockBatch,
    PPEStockMovement,
    ...
)
```

And add both names to the `__all__` list (near line 591 where `"PPEStockBatch"`, `"PPEStockMovement"` are):

```python
    "PPEInventoryCount",
    "PPEInventoryCountLine",
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest backend/tests/test_ppe_inventory_count_model.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Lint + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/models/ppe.py backend/app/models/models.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/models/ppe.py backend/app/models/models.py backend/tests/test_ppe_inventory_count_model.py
git add backend/app/models/ppe.py backend/app/models/models.py backend/tests/test_ppe_inventory_count_model.py
git commit -m "feat(p10-06): PPEInventoryCount(+Line) ORM models"
```

---

### Task 2: Additive migration `wa06`

**Files:**
- Create: `backend/app/migrations/versions/20260703_wa06_ppe_inventory_count.py`
- Test: `backend/tests/test_wa06_ppe_inventory_count_migration.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_wa06_ppe_inventory_count_migration.py` (static test — mirrors `test_wa05...`, extended to two tables per the `wa04` two-string style):

```python
"""wa06 creates the additive ppe_inventory_count(+_line) tables (P10-06)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260703_wa06_ppe_inventory_count.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa06_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIGRATION.exists(), "wa06 migration missing"


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260703_wa06_ppe_inventory_count"
    assert mod.down_revision == "20260703_wa05_ppeitem_min_stock"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_creates_and_drops_both_tables():
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "ppe_inventory_count"' in src
    assert 'op.create_table(\n        "ppe_inventory_count_line"' in src
    assert 'op.drop_table("ppe_inventory_count_line")' in src
    assert 'op.drop_table("ppe_inventory_count")' in src
    assert "add_column" not in src  # purely new tables, no existing-table mutation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/test_wa06_ppe_inventory_count_migration.py -q`
Expected: FAIL — `test_migration_file_exists` asserts False (file absent).

- [ ] **Step 3: Write the migration**

Create `backend/app/migrations/versions/20260703_wa06_ppe_inventory_count.py`. Table columns mirror `TenantBaseModel` (+ `SoftDeleteMixin` on the header) exactly as `wa04` did (`id/tenant_id/version/created_at/updated_at`, plus `deleted_at` for the header). Parent table first; child second (FK order):

```python
"""ppe inventory count (stocktake) tables (P10-06 / honest остатки).

Additive: creates ppe_inventory_count (header) + ppe_inventory_count_line
(per-batch snapshot). No column added to existing tables, no data backfill.
``status`` is VARCHAR, not a PG enum (enum-parity convention). Chains off wa05.

Revision ID: 20260703_wa06_ppe_inventory_count
Revises: 20260703_wa05_ppeitem_min_stock
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260703_wa06_ppe_inventory_count"
down_revision = "20260703_wa05_ppeitem_min_stock"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_inventory_count",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("scope_item_id", sa.String(length=36), nullable=True),
        sa.Column("scope_location", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["scope_item_id"], ["ppeitem.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ppe_inventory_count_tenant_id"), "ppe_inventory_count", ["tenant_id"]
    )
    op.create_table(
        "ppe_inventory_count_line",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("count_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("system_qty", sa.Integer(), nullable=False),
        sa.Column("counted_qty", sa.Integer(), nullable=True),
        sa.Column("adjustment_movement_id", sa.String(length=36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(
            ["count_id"], ["ppe_inventory_count.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["item_id"], ["ppeitem.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["ppe_stock_batch.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "count_id", "batch_id", name="uq_ppe_inv_count_line_batch"
        ),
    )
    op.create_index(
        op.f("ix_ppe_inventory_count_line_tenant_id"),
        "ppe_inventory_count_line",
        ["tenant_id"],
    )
    op.create_index(
        "ix_ppe_inventory_count_line_count",
        "ppe_inventory_count_line",
        ["tenant_id", "count_id"],
    )
    op.create_index(
        "ix_ppe_inventory_count_line_batch",
        "ppe_inventory_count_line",
        ["tenant_id", "batch_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ppe_inventory_count_line_batch", table_name="ppe_inventory_count_line"
    )
    op.drop_index(
        "ix_ppe_inventory_count_line_count", table_name="ppe_inventory_count_line"
    )
    op.drop_index(
        op.f("ix_ppe_inventory_count_line_tenant_id"),
        table_name="ppe_inventory_count_line",
    )
    op.drop_table("ppe_inventory_count_line")
    op.drop_index(
        op.f("ix_ppe_inventory_count_tenant_id"), table_name="ppe_inventory_count"
    )
    op.drop_table("ppe_inventory_count")
```

- [ ] **Step 4: Run the test + confirm single head**

Run: `pytest backend/tests/test_wa06_ppe_inventory_count_migration.py -q`
Expected: PASS (4 tests).

Confirm the chain has a single head (should print exactly `20260703_wa06_ppe_inventory_count (head)`):
Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m alembic -c backend/app/migrations/alembic.ini heads`
(If `alembic` CLI is unavailable locally, skip — the PG16 gate in Task 13 validates the chain. Note the skip in your output.)

- [ ] **Step 5: black (formatting must hold for the string-match test) + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/migrations/versions/20260703_wa06_ppe_inventory_count.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/migrations/versions/20260703_wa06_ppe_inventory_count.py
pytest backend/tests/test_wa06_ppe_inventory_count_migration.py -q
git add backend/app/migrations/versions/20260703_wa06_ppe_inventory_count.py backend/tests/test_wa06_ppe_inventory_count_migration.py
git commit -m "feat(p10-06): additive wa06 migration for ppe_inventory_count(+line)"
```

> **Note:** if `black` rewraps `op.create_table(` differently, re-check the `'op.create_table(\n        "..."'` assertions still match; adjust the test strings to the black output, not the other way around.

---

### Task 3: Additive `ref_type`/`ref_id` on `record_movement`

**Files:**
- Modify: `backend/app/modules/ppe/stock.py:163-200` (`record_movement`)
- Test: `tests/api/test_ppe_stock_movements_service.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_ppe_stock_movements_service.py` (reuses the file's existing `_item_and_batch` helper and imports):

```python
@pytest.mark.asyncio
async def test_record_movement_persists_ref_type_and_id(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)

        movement = await record_movement(
            session,
            tenant_id=tenant.id,
            batch_id=batch.id,
            kind="adjustment",
            quantity=7,
            reason="inventory abc",
            ref_type="ppe_inventory_count",
            ref_id="count-123",
        )

    assert movement.ref_type == "ppe_inventory_count"
    assert movement.ref_id == "count-123"
    assert movement.quantity_delta == -3  # 10 -> 7 absolute
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_ppe_stock_movements_service.py::test_record_movement_persists_ref_type_and_id -q`
Expected: FAIL — `TypeError: record_movement() got an unexpected keyword argument 'ref_type'`.

- [ ] **Step 3: Extend `record_movement`**

In `backend/app/modules/ppe/stock.py`, change the `record_movement` signature (currently ends `occurred_at: datetime | None = None,`) to add the two optional params, and pass them through in the `_write_movement` call. `_write_movement` already accepts `ref_type`/`ref_id` (lines 133-136):

```python
async def record_movement(
    session: AsyncSession,
    *,
    tenant_id: str,
    batch_id: str,
    kind: str,
    quantity: int,
    reason: str | None = None,
    occurred_at: datetime | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> PPEStockMovement:
```

and the trailing return call:

```python
    return await _write_movement(
        session,
        tenant_id=tenant_id,
        batch=batch,
        kind=kind,
        delta=delta,
        reason=reason,
        occurred_at=occurred_at,
        ref_type=ref_type,
        ref_id=ref_id,
    )
```

- [ ] **Step 4: Run tests (new + regression on the file)**

Run: `pytest tests/api/test_ppe_stock_movements_service.py -q`
Expected: PASS (all existing tests + the new one — the two new params default to `None`, so existing callers are unaffected).

- [ ] **Step 5: Lint + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/modules/ppe/stock.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/modules/ppe/stock.py tests/api/test_ppe_stock_movements_service.py
git add backend/app/modules/ppe/stock.py tests/api/test_ppe_stock_movements_service.py
git commit -m "feat(p10-06): additive ref_type/ref_id passthrough on record_movement"
```

---

### Task 4: Service — `create_count` + `get_count_detail`

**Files:**
- Create: `backend/app/modules/ppe/inventory.py`
- Test: `tests/api/test_ppe_inventory_count_service.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_ppe_inventory_count_service.py`:

```python
"""Service tests for the PPE inventory-count workflow (P10-06)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.ppe import PPEItem, PPEStockBatch
from app.modules.ppe.inventory import create_count, get_count_detail
from tests.utils.factories import TestDataFactory

NOW = datetime(2026, 7, 3, tzinfo=timezone.utc)


async def _item(session, tenant_id, *, name):
    item = PPEItem(tenant_id=tenant_id, name=name)
    session.add(item)
    await session.flush()
    return item


async def _batch(session, tenant_id, item_id, *, batch_no, qty, location=None):
    batch = PPEStockBatch(
        tenant_id=tenant_id,
        item_id=item_id,
        batch_no=batch_no,
        quantity=qty,
        location=location,
    )
    session.add(batch)
    await session.flush()
    return batch


@pytest.mark.asyncio
async def test_create_count_seeds_line_per_batch_with_snapshot(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        await _batch(session, tenant.id, item.id, batch_no="B-2", qty=4)

        count = await create_count(session, tenant_id=tenant.id, note="июль")
        detail = await get_count_detail(session, tenant.id, count.id)

    assert count.status == "draft"
    assert detail.line_count == 2
    assert {line.system_qty for line in detail.lines} == {10, 4}
    assert all(line.counted_qty is None for line in detail.lines)
    assert all(line.delta is None for line in detail.lines)
    # on_hand mirrors the live batch quantity at read time
    assert {line.on_hand for line in detail.lines} == {10, 4}


@pytest.mark.asyncio
async def test_create_count_scope_filters_by_item_and_location(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item_a = await _item(session, tenant.id, name="A")
        item_b = await _item(session, tenant.id, name="B")
        await _batch(session, tenant.id, item_a.id, batch_no="A-1", qty=5, location="Склад-1")
        await _batch(session, tenant.id, item_a.id, batch_no="A-2", qty=5, location="Склад-2")
        await _batch(session, tenant.id, item_b.id, batch_no="B-1", qty=5, location="Склад-1")

        by_item = await create_count(session, tenant_id=tenant.id, scope_item_id=item_a.id)
        by_loc = await create_count(session, tenant_id=tenant.id, scope_location="Склад-1")
        d_item = await get_count_detail(session, tenant.id, by_item.id)
        d_loc = await get_count_detail(session, tenant.id, by_loc.id)

    assert d_item.line_count == 2  # both item_a batches
    assert d_loc.line_count == 2  # both Склад-1 batches (across items)


@pytest.mark.asyncio
async def test_create_count_no_matching_batches_is_empty(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id, scope_location="Нет-такой")
        detail = await get_count_detail(session, tenant.id, count.id)

    assert detail.line_count == 0
    assert detail.lines == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_ppe_inventory_count_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.modules.ppe.inventory'`.

- [ ] **Step 3: Create the service module with `create_count`, `get_count_detail`, and the view dataclasses**

Create `backend/app/modules/ppe/inventory.py`:

```python
"""PPE inventory count (stocktake) workflow (P10-06).

Two-phase count session (``draft`` → ``applied`` / ``cancelled``) layered over the
honest-balance ledger. ``apply`` reconciles physical counts into ``adjustment``
movements through ``record_movement`` — the single sanctioned mutation point for
``batch.quantity``. This module never mutates stock quantity directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ppe import (
    PPEInventoryCount,
    PPEInventoryCountLine,
    PPEItem,
    PPEStockBatch,
)
from app.modules.ppe.stock import KIND_ADJUSTMENT, record_movement

INVENTORY_REF_TYPE = "ppe_inventory_count"


class InventoryCountNotFound(Exception):
    """Raised when a count/line does not exist for the tenant."""

    def __init__(self, count_id: str) -> None:
        super().__init__(f"PPE inventory count not found: {count_id}")
        self.count_id = count_id


class InventoryCountNotDraft(Exception):
    """Raised when a mutating action targets a non-``draft`` count."""

    def __init__(self, count_id: str, status: str) -> None:
        super().__init__(f"inventory count {count_id} is not draft (status={status})")
        self.count_id = count_id
        self.status = status


@dataclass(slots=True, frozen=True)
class CountLineView:
    id: str
    batch_id: str
    item_id: str
    batch_no: str
    location: str | None
    item_name: str
    system_qty: int
    counted_qty: int | None
    on_hand: int
    delta: int | None
    adjustment_movement_id: str | None


@dataclass(slots=True, frozen=True)
class CountDetailView:
    count: PPEInventoryCount
    lines: list[CountLineView]
    line_count: int
    counted_count: int
    diff_count: int


@dataclass(slots=True, frozen=True)
class CountSummaryView:
    count: PPEInventoryCount
    line_count: int
    counted_count: int


async def _load_count(
    session: AsyncSession, tenant_id: str, count_id: str
) -> PPEInventoryCount:
    stmt = select(PPEInventoryCount).where(
        PPEInventoryCount.id == count_id,
        PPEInventoryCount.tenant_id == tenant_id,
        PPEInventoryCount.deleted_at.is_(None),
    )
    count = (await session.execute(stmt)).scalar_one_or_none()
    if count is None:
        raise InventoryCountNotFound(count_id)
    return count


async def create_count(
    session: AsyncSession,
    tenant_id: str,
    *,
    scope_item_id: str | None = None,
    scope_location: str | None = None,
    note: str | None = None,
) -> PPEInventoryCount:
    """Open a draft count and seed one line per active batch under the filter."""
    count = PPEInventoryCount(
        tenant_id=tenant_id,
        status="draft",
        scope_item_id=scope_item_id,
        scope_location=scope_location,
        note=note,
    )
    session.add(count)
    await session.flush()

    stmt = select(PPEStockBatch).where(
        PPEStockBatch.tenant_id == tenant_id,
        PPEStockBatch.deleted_at.is_(None),
    )
    if scope_item_id is not None:
        stmt = stmt.where(PPEStockBatch.item_id == scope_item_id)
    if scope_location is not None:
        stmt = stmt.where(PPEStockBatch.location == scope_location)
    batches = list((await session.execute(stmt)).scalars().all())
    for batch in batches:
        session.add(
            PPEInventoryCountLine(
                tenant_id=tenant_id,
                count_id=count.id,
                item_id=batch.item_id,
                batch_id=batch.id,
                system_qty=batch.quantity,
                counted_qty=None,
            )
        )
    await session.flush()
    return count


async def get_count_detail(
    session: AsyncSession, tenant_id: str, count_id: str
) -> CountDetailView:
    """Load a count with per-line live ``on_hand``/``delta`` (this is the preview).

    Batched queries only (no lazy ``line.batch``): no N+1, no soft-deleted leak.
    A line whose batch is soft-deleted/absent reports ``on_hand=0`` and ``delta=None``.
    """
    count = await _load_count(session, tenant_id, count_id)
    lines = list(
        (
            await session.execute(
                select(PPEInventoryCountLine)
                .where(
                    PPEInventoryCountLine.tenant_id == tenant_id,
                    PPEInventoryCountLine.count_id == count_id,
                )
                .order_by(PPEInventoryCountLine.id.asc())
            )
        )
        .scalars()
        .all()
    )
    batch_ids = [line.batch_id for line in lines]
    item_ids = {line.item_id for line in lines}

    on_hand: dict[str, int] = {}
    batch_no: dict[str, str] = {}
    location: dict[str, str | None] = {}
    if batch_ids:
        rows = (
            await session.execute(
                select(
                    PPEStockBatch.id,
                    PPEStockBatch.quantity,
                    PPEStockBatch.batch_no,
                    PPEStockBatch.location,
                ).where(
                    PPEStockBatch.id.in_(batch_ids),
                    PPEStockBatch.deleted_at.is_(None),
                )
            )
        ).all()
        for bid, qty, bno, loc in rows:
            on_hand[bid] = int(qty or 0)
            batch_no[bid] = bno
            location[bid] = loc

    names: dict[str, str] = {}
    if item_ids:
        name_rows = (
            await session.execute(
                select(PPEItem.id, PPEItem.name).where(PPEItem.id.in_(item_ids))
            )
        ).all()
        names = {iid: name for iid, name in name_rows}

    views: list[CountLineView] = []
    counted_count = 0
    diff_count = 0
    for line in lines:
        oh = on_hand.get(line.batch_id, 0)
        if line.counted_qty is not None:
            counted_count += 1
            delta: int | None = line.counted_qty - oh
            if delta != 0:
                diff_count += 1
        else:
            delta = None
        views.append(
            CountLineView(
                id=line.id,
                batch_id=line.batch_id,
                item_id=line.item_id,
                batch_no=batch_no.get(line.batch_id, ""),
                location=location.get(line.batch_id),
                item_name=names.get(line.item_id, ""),
                system_qty=line.system_qty,
                counted_qty=line.counted_qty,
                on_hand=oh,
                delta=delta,
                adjustment_movement_id=line.adjustment_movement_id,
            )
        )
    return CountDetailView(
        count=count,
        lines=views,
        line_count=len(lines),
        counted_count=counted_count,
        diff_count=diff_count,
    )
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/api/test_ppe_inventory_count_service.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Lint + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/modules/ppe/inventory.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/modules/ppe/inventory.py tests/api/test_ppe_inventory_count_service.py
git add backend/app/modules/ppe/inventory.py tests/api/test_ppe_inventory_count_service.py
git commit -m "feat(p10-06): inventory service — create_count + get_count_detail"
```

---

### Task 5: Service — `set_line_counts` + `list_counts`

**Files:**
- Modify: `backend/app/modules/ppe/inventory.py`
- Test: `tests/api/test_ppe_inventory_count_service.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_ppe_inventory_count_service.py` (add `list_counts, set_line_counts` to the existing `from app.modules.ppe.inventory import ...` line):

```python
@pytest.mark.asyncio
async def test_set_line_counts_updates_only_named_lines(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import set_line_counts

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        await _batch(session, tenant.id, item.id, batch_no="B-2", qty=4)
        count = await create_count(session, tenant_id=tenant.id)
        detail = await get_count_detail(session, tenant.id, count.id)
        first = detail.lines[0]

        await set_line_counts(
            session, tenant_id=tenant.id, count_id=count.id, entries=[(first.id, 8)]
        )
        after = await get_count_detail(session, tenant.id, count.id)

    counted = {line.id: line.counted_qty for line in after.lines}
    assert counted[first.id] == 8
    assert after.counted_count == 1
    # 8 counted vs 10 on_hand -> delta -2 -> one diff
    assert after.diff_count == 1


@pytest.mark.asyncio
async def test_set_line_counts_rejects_unknown_line(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import InventoryCountNotFound, set_line_counts

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)
        with pytest.raises(InventoryCountNotFound):
            await set_line_counts(
                session, tenant_id=tenant.id, count_id=count.id, entries=[("nope", 1)]
            )


@pytest.mark.asyncio
async def test_list_counts_filters_by_status_and_counts_lines(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import list_counts

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        count = await create_count(session, tenant_id=tenant.id)
        detail = await get_count_detail(session, tenant.id, count.id)
        from app.modules.ppe.inventory import set_line_counts

        await set_line_counts(
            session, tenant_id=tenant.id, count_id=count.id, entries=[(detail.lines[0].id, 9)]
        )
        await session.commit()
    async with sessionmaker() as session:
        drafts, total = await list_counts(session, tenant.id, status="draft")
        applied, _ = await list_counts(session, tenant.id, status="applied")

    assert total == 1
    assert drafts[0].line_count == 1
    assert drafts[0].counted_count == 1
    assert applied == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_ppe_inventory_count_service.py -k "set_line_counts or list_counts" -q`
Expected: FAIL — `ImportError: cannot import name 'set_line_counts'`.

- [ ] **Step 3: Add `set_line_counts` and `list_counts`**

Append to `backend/app/modules/ppe/inventory.py`:

```python
async def set_line_counts(
    session: AsyncSession,
    tenant_id: str,
    *,
    count_id: str,
    entries: list[tuple[str, int | None]],
) -> PPEInventoryCount:
    """Bulk-set ``counted_qty`` on a draft count's lines. ``None`` clears a count."""
    count = await _load_count(session, tenant_id, count_id)
    if count.status != "draft":
        raise InventoryCountNotDraft(count_id, count.status)

    line_ids = [line_id for line_id, _ in entries]
    by_id: dict[str, PPEInventoryCountLine] = {}
    if line_ids:
        rows = (
            await session.execute(
                select(PPEInventoryCountLine).where(
                    PPEInventoryCountLine.tenant_id == tenant_id,
                    PPEInventoryCountLine.count_id == count_id,
                    PPEInventoryCountLine.id.in_(line_ids),
                )
            )
        ).scalars().all()
        by_id = {line.id: line for line in rows}

    for line_id, counted_qty in entries:
        line = by_id.get(line_id)
        if line is None:
            raise InventoryCountNotFound(line_id)
        line.counted_qty = counted_qty
    await session.flush()
    return count


async def list_counts(
    session: AsyncSession,
    tenant_id: str,
    *,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[CountSummaryView], int]:
    """Paginated counts (newest first) with cheap per-count line/counted tallies."""
    base = select(PPEInventoryCount).where(
        PPEInventoryCount.tenant_id == tenant_id,
        PPEInventoryCount.deleted_at.is_(None),
    )
    if status is not None:
        base = base.where(PPEInventoryCount.status == status)
    stmt = (
        base.order_by(
            PPEInventoryCount.created_at.desc(), PPEInventoryCount.id.desc()
        )
        .limit(limit)
        .offset(offset)
    )
    counts = list((await session.execute(stmt)).scalars().all())
    total = (
        await session.execute(select(func.count()).select_from(base.subquery()))
    ).scalar_one()

    tallies: dict[str, tuple[int, int]] = {}
    count_ids = [c.id for c in counts]
    if count_ids:
        rows = (
            await session.execute(
                select(
                    PPEInventoryCountLine.count_id,
                    func.count(),
                    func.count(PPEInventoryCountLine.counted_qty),
                )
                .where(
                    PPEInventoryCountLine.tenant_id == tenant_id,
                    PPEInventoryCountLine.count_id.in_(count_ids),
                )
                .group_by(PPEInventoryCountLine.count_id)
            )
        ).all()
        tallies = {cid: (int(lc or 0), int(cc or 0)) for cid, lc, cc in rows}

    views = [
        CountSummaryView(
            count=c,
            line_count=tallies.get(c.id, (0, 0))[0],
            counted_count=tallies.get(c.id, (0, 0))[1],
        )
        for c in counts
    ]
    return views, int(total or 0)
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/api/test_ppe_inventory_count_service.py -q`
Expected: PASS (6 tests total in the file now).

- [ ] **Step 5: Lint + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/modules/ppe/inventory.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/modules/ppe/inventory.py tests/api/test_ppe_inventory_count_service.py
git add backend/app/modules/ppe/inventory.py tests/api/test_ppe_inventory_count_service.py
git commit -m "feat(p10-06): inventory service — set_line_counts + list_counts"
```

---

### Task 6: Service — `apply_count` + `cancel_count`

**Files:**
- Modify: `backend/app/modules/ppe/inventory.py`
- Test: `tests/api/test_ppe_inventory_count_service.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_ppe_inventory_count_service.py`:

```python
@pytest.mark.asyncio
async def test_apply_emits_adjustments_only_for_changed_counted_lines(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import apply_count, set_line_counts
    from app.models.ppe import PPEStockMovement
    from sqlalchemy import select as _select

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        b_low = await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)   # count 8 -> adjust
        b_same = await _batch(session, tenant.id, item.id, batch_no="B-2", qty=5)   # count 5 -> skip
        b_skip = await _batch(session, tenant.id, item.id, batch_no="B-3", qty=3)   # uncounted -> skip
        count = await create_count(session, tenant_id=tenant.id)
        detail = await get_count_detail(session, tenant.id, count.id)
        line_by_batch = {line.batch_id: line.id for line in detail.lines}

        await set_line_counts(
            session,
            tenant_id=tenant.id,
            count_id=count.id,
            entries=[(line_by_batch[b_low.id], 8), (line_by_batch[b_same.id], 5)],
        )
        applied = await apply_count(
            session, tenant_id=tenant.id, count_id=count.id, now=NOW
        )
        await session.refresh(b_low)
        await session.refresh(b_same)
        await session.refresh(b_skip)
        movements = list(
            (
                await _select and await session.execute(
                    _select(PPEStockMovement).where(
                        PPEStockMovement.tenant_id == tenant.id,
                        PPEStockMovement.kind == "adjustment",
                    )
                )
            ).scalars().all()
        )

    assert applied.status == "applied"
    assert applied.applied_at == NOW
    assert b_low.quantity == 8   # adjusted to counted
    assert b_same.quantity == 5  # unchanged (zero delta -> no movement)
    assert b_skip.quantity == 3  # uncounted -> untouched
    assert len(movements) == 1
    assert movements[0].ref_type == "ppe_inventory_count"
    assert movements[0].ref_id == count.id


@pytest.mark.asyncio
async def test_apply_uses_live_on_hand_not_snapshot(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import apply_count, set_line_counts
    from app.modules.ppe.stock import record_movement

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска")
        batch = await _batch(session, tenant.id, item.id, batch_no="B-1", qty=10)
        count = await create_count(session, tenant_id=tenant.id)  # snapshot system_qty=10
        detail = await get_count_detail(session, tenant.id, count.id)
        # stock moves AFTER the snapshot: a writeoff of 4 -> live on_hand=6
        await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="writeoff", quantity=4
        )
        await set_line_counts(
            session,
            tenant_id=tenant.id,
            count_id=count.id,
            entries=[(detail.lines[0].id, 9)],
        )
        await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)
        await session.refresh(batch)

    assert batch.quantity == 9  # set-to-absolute from LIVE 6, not snapshot 10


@pytest.mark.asyncio
async def test_apply_twice_is_rejected(sessionmaker, data_factory: TestDataFactory):
    from app.modules.ppe.inventory import (
        InventoryCountNotDraft,
        apply_count,
    )

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)
        await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)
        with pytest.raises(InventoryCountNotDraft):
            await apply_count(session, tenant_id=tenant.id, count_id=count.id, now=NOW)


@pytest.mark.asyncio
async def test_cancel_sets_status_and_writes_no_movements(
    sessionmaker, data_factory: TestDataFactory
):
    from app.modules.ppe.inventory import cancel_count

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        count = await create_count(session, tenant_id=tenant.id)
        cancelled = await cancel_count(session, tenant_id=tenant.id, count_id=count.id)

    assert cancelled.status == "cancelled"
```

> **Note on the `movements` query in the first test:** replace the awkward `await _select and ...` guard with a plain execute — written verbatim below so there is no ambiguity. If the engineer copied the block above, use this exact query instead:
> ```python
>         result = await session.execute(
>             _select(PPEStockMovement).where(
>                 PPEStockMovement.tenant_id == tenant.id,
>                 PPEStockMovement.kind == "adjustment",
>             )
>         )
>         movements = list(result.scalars().all())
> ```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_ppe_inventory_count_service.py -k "apply or cancel" -q`
Expected: FAIL — `ImportError: cannot import name 'apply_count'`.

- [ ] **Step 3: Add `apply_count` and `cancel_count`**

Append to `backend/app/modules/ppe/inventory.py`:

```python
async def apply_count(
    session: AsyncSession, tenant_id: str, *, count_id: str, now: datetime
) -> PPEInventoryCount:
    """Reconcile physical counts into ``adjustment`` movements and freeze the count.

    Emits an adjustment only for counted lines whose ``counted_qty`` differs from the
    **live** batch on-hand (set-to-absolute via ``record_movement``). Uncounted lines,
    zero-delta lines, and lines whose batch is soft-deleted are skipped. Concurrent
    applies are guarded by the ``VersionedMixin`` optimistic lock on the header (the
    losing flush raises ``StaleDataError``, surfaced as 409 at the route).
    """
    count = await _load_count(session, tenant_id, count_id)
    if count.status != "draft":
        raise InventoryCountNotDraft(count_id, count.status)

    lines = list(
        (
            await session.execute(
                select(PPEInventoryCountLine).where(
                    PPEInventoryCountLine.tenant_id == tenant_id,
                    PPEInventoryCountLine.count_id == count_id,
                )
            )
        )
        .scalars()
        .all()
    )
    batch_ids = [line.batch_id for line in lines]
    live: dict[str, int] = {}
    if batch_ids:
        rows = (
            await session.execute(
                select(PPEStockBatch.id, PPEStockBatch.quantity).where(
                    PPEStockBatch.id.in_(batch_ids),
                    PPEStockBatch.deleted_at.is_(None),
                )
            )
        ).all()
        live = {bid: int(qty or 0) for bid, qty in rows}

    for line in lines:
        if line.counted_qty is None:
            continue
        if line.batch_id not in live:
            continue  # batch soft-deleted after seeding
        if line.counted_qty == live[line.batch_id]:
            continue  # zero delta — advisory skip; record_movement is source of truth
        movement = await record_movement(
            session,
            tenant_id=tenant_id,
            batch_id=line.batch_id,
            kind=KIND_ADJUSTMENT,
            quantity=line.counted_qty,
            reason=f"inventory {count_id}",
            ref_type=INVENTORY_REF_TYPE,
            ref_id=count_id,
        )
        line.adjustment_movement_id = movement.id

    count.status = "applied"
    count.applied_at = now
    await session.flush()
    return count


async def cancel_count(
    session: AsyncSession, tenant_id: str, *, count_id: str
) -> PPEInventoryCount:
    """Cancel a draft count. Emits no movements."""
    count = await _load_count(session, tenant_id, count_id)
    if count.status != "draft":
        raise InventoryCountNotDraft(count_id, count.status)
    count.status = "cancelled"
    await session.flush()
    return count
```

- [ ] **Step 4: Run the full service test file**

Run: `pytest tests/api/test_ppe_inventory_count_service.py -q`
Expected: PASS (10 tests).

- [ ] **Step 5: Lint + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/modules/ppe/inventory.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/modules/ppe/inventory.py tests/api/test_ppe_inventory_count_service.py
git add backend/app/modules/ppe/inventory.py tests/api/test_ppe_inventory_count_service.py
git commit -m "feat(p10-06): inventory service — apply_count (live-delta adjustments) + cancel_count"
```

---

### Task 7: Pydantic schemas

**Files:**
- Modify: `backend/app/schemas/ppe.py` (append after `PPEStockMovementPage`, ~line 313)
- Test: `tests/unit/test_ppe_inventory_count_schema.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_ppe_inventory_count_schema.py`:

```python
"""Schema shape for the PPE inventory-count slice (P10-06)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ppe import (
    PPEInventoryCountCreate,
    PPEInventoryCountDetail,
    PPEInventoryCountLinesUpdate,
)


def test_create_defaults_are_optional():
    payload = PPEInventoryCountCreate()
    assert payload.scope_item_id is None
    assert payload.scope_location is None
    assert payload.note is None


def test_lines_update_accepts_null_and_nonnegative():
    upd = PPEInventoryCountLinesUpdate(
        entries=[{"line_id": "l1", "counted_qty": 0}, {"line_id": "l2", "counted_qty": None}]
    )
    assert upd.entries[0].counted_qty == 0
    assert upd.entries[1].counted_qty is None


def test_lines_update_rejects_negative_counted():
    with pytest.raises(ValidationError):
        PPEInventoryCountLinesUpdate(entries=[{"line_id": "l1", "counted_qty": -1}])


def test_detail_carries_diff_count_and_lines():
    fields = set(PPEInventoryCountDetail.model_fields.keys())
    assert {"diff_count", "lines", "line_count", "counted_count", "status"} <= fields
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_ppe_inventory_count_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'PPEInventoryCountCreate'`.

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas/ppe.py` (after `PPEStockMovementPage`, end of file). `BaseSchema`, `Field`, `datetime` are already imported at the top:

```python
class PPEInventoryCountCreate(BaseSchema):
    scope_item_id: str | None = None
    scope_location: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=255)


class PPEInventoryCountLineInput(BaseSchema):
    line_id: str
    # None = not counted (skipped at apply); 0 = counted-zero (write-off);
    # ge=0 applies only when an int is supplied.
    counted_qty: int | None = Field(default=None, ge=0)


class PPEInventoryCountLinesUpdate(BaseSchema):
    entries: list[PPEInventoryCountLineInput]


class PPEInventoryCountLineRead(BaseSchema):
    id: str
    batch_id: str
    item_id: str
    batch_no: str
    location: str | None
    item_name: str
    system_qty: int
    counted_qty: int | None
    on_hand: int
    delta: int | None
    adjustment_movement_id: str | None


class PPEInventoryCountRead(BaseSchema):
    id: str
    status: str
    scope_item_id: str | None
    scope_location: str | None
    note: str | None
    applied_at: datetime | None
    created_at: datetime
    line_count: int
    counted_count: int


class PPEInventoryCountDetail(PPEInventoryCountRead):
    diff_count: int
    lines: list[PPEInventoryCountLineRead]


class PPEInventoryCountPage(BaseSchema):
    items: list[PPEInventoryCountRead]
    total: int
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/unit/test_ppe_inventory_count_schema.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Lint + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/schemas/ppe.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/schemas/ppe.py tests/unit/test_ppe_inventory_count_schema.py
git add backend/app/schemas/ppe.py tests/unit/test_ppe_inventory_count_schema.py
git commit -m "feat(p10-06): inventory-count Pydantic schemas"
```

---

### Task 8: Routes — create + list + get(detail)

**Files:**
- Modify: `backend/app/api/routes/ppe.py` (imports + append after `list_stock_movements`, ~line 1144)
- Test: `tests/api/test_ppe_inventory_count_api.py`

- [ ] **Step 1: Write the failing test**

Create `tests/api/test_ppe_inventory_count_api.py`:

```python
"""API tests for the PPE inventory-count slice (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _set_warehouse_flag(sessionmaker, data_factory: TestDataFactory, *, on: bool) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (
            await session.execute(select(Feature).where(Feature.code == "warehouse"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        await session.commit()


async def _seed_item(async_client: AsyncClient, headers: dict, *, name: str = "Каска") -> str:
    resp = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


async def _seed_batch(
    async_client: AsyncClient, headers: dict, item_id: str, *, batch_no: str, qty: int
) -> str:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": batch_no, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_create_seeds_lines_and_get_returns_detail(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id, batch_no="B-1", qty=10)

    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={"note": "июль"}, headers=headers
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    body = created.json()
    assert body["status"] == "draft"
    assert body["line_count"] == 1
    assert len(body["lines"]) == 1
    assert body["lines"][0]["system_qty"] == 10
    assert body["lines"][0]["counted_qty"] is None
    count_id = body["id"]

    listed = await async_client.get("/api/v1/ppe/stock/inventory/counts", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(c["id"] == count_id for c in listed.json()["items"])

    fetched = await async_client.get(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}", headers=headers
    )
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["lines"][0]["on_hand"] == 10


@pytest.mark.asyncio
async def test_list_etag_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    first = await async_client.get("/api/v1/ppe/stock/inventory/counts", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]
    second = await async_client.get(
        "/api/v1/ppe/stock/inventory/counts", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_counts_gated_by_warehouse_flag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    await _set_warehouse_flag(sessionmaker, data_factory, on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/inventory/counts", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert "warehouse" in resp.text.lower()


@pytest.mark.asyncio
async def test_get_cross_tenant_is_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()
    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers_a
    )
    count_id = created.json()["id"]

    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta@example.com"
    )
    fetched = await async_client.get(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}", headers=headers_b
    )
    assert fetched.status_code == status.HTTP_404_NOT_FOUND
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_ppe_inventory_count_api.py -q`
Expected: FAIL — 404 for `POST /api/v1/ppe/stock/inventory/counts` (route not registered) → assertion errors.

- [ ] **Step 3: Add imports + the three routes**

In `backend/app/api/routes/ppe.py`:

(a) Add the service import near the other `app.modules.ppe.*` imports (after the `from app.modules.ppe.stock import (...)` block at lines 44-48):

```python
from app.modules.ppe.inventory import (
    InventoryCountNotDraft,
    InventoryCountNotFound,
    apply_count,
    cancel_count,
    create_count,
    get_count_detail,
    list_counts,
    set_line_counts,
)
```

(b) Add `StaleDataError` import (used by the apply route in Task 9) after the existing sqlalchemy imports at line 9:

```python
from sqlalchemy.orm.exc import StaleDataError
```

(c) Add the new schema names to the `from app.schemas.ppe import (...)` group (lines 49-81):

```python
    PPEInventoryCountCreate,
    PPEInventoryCountDetail,
    PPEInventoryCountLineRead,
    PPEInventoryCountLinesUpdate,
    PPEInventoryCountPage,
    PPEInventoryCountRead,
```

(d) Append these response-builder helpers + the three routes **after `list_stock_movements` (line 1144), before the `# --- 766н` comment (line 1147)**:

```python
def _inventory_count_read(view) -> PPEInventoryCountRead:
    c = view.count
    return PPEInventoryCountRead(
        id=c.id,
        status=c.status,
        scope_item_id=c.scope_item_id,
        scope_location=c.scope_location,
        note=c.note,
        applied_at=c.applied_at,
        created_at=c.created_at,
        line_count=view.line_count,
        counted_count=view.counted_count,
    )


def _inventory_count_detail(detail) -> PPEInventoryCountDetail:
    c = detail.count
    return PPEInventoryCountDetail(
        id=c.id,
        status=c.status,
        scope_item_id=c.scope_item_id,
        scope_location=c.scope_location,
        note=c.note,
        applied_at=c.applied_at,
        created_at=c.created_at,
        line_count=detail.line_count,
        counted_count=detail.counted_count,
        diff_count=detail.diff_count,
        lines=[
            PPEInventoryCountLineRead(
                id=v.id,
                batch_id=v.batch_id,
                item_id=v.item_id,
                batch_no=v.batch_no,
                location=v.location,
                item_name=v.item_name,
                system_qty=v.system_qty,
                counted_qty=v.counted_qty,
                on_hand=v.on_hand,
                delta=v.delta,
                adjustment_movement_id=v.adjustment_movement_id,
            )
            for v in detail.lines
        ],
    )


@router.post(
    "/stock/inventory/counts",
    response_model=PPEInventoryCountDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("create", "ppe_inventory_count")
async def create_inventory_count(
    payload: PPEInventoryCountCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEInventoryCountDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    if payload.scope_item_id is not None:
        await _get_item(session, tenant, payload.scope_item_id)
    count = await create_count(
        session,
        tenant_id=tenant.id,
        scope_item_id=payload.scope_item_id,
        scope_location=payload.scope_location,
        note=payload.note,
    )
    detail = await get_count_detail(session, tenant.id, count.id)
    return _inventory_count_detail(detail)


@router.get(
    "/stock/inventory/counts",
    response_model=PPEInventoryCountPage,
    dependencies=[WarehouseFeatureGate],
)
async def list_inventory_counts(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEInventoryCountPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    views, total = await list_counts(
        session, tenant.id, status=status_filter, limit=limit, offset=offset
    )
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=[v.count for v in views],
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("status", status_filter or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PPEInventoryCountPage(
        items=[_inventory_count_read(v) for v in views], total=total
    )


@router.get(
    "/stock/inventory/counts/{count_id}",
    response_model=PPEInventoryCountDetail,
    dependencies=[WarehouseFeatureGate],
)
async def get_inventory_count(
    count_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PPEInventoryCountDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        detail = await get_count_detail(session, tenant.id, count_id)
    except InventoryCountNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return _inventory_count_detail(detail)
```

- [ ] **Step 4: Run the test**

Run: `pytest tests/api/test_ppe_inventory_count_api.py -q`
Expected: PASS (4 tests). (`InventoryCountNotDraft`, `apply_count`, `cancel_count`, `set_line_counts` are imported now but used in Task 9 — that's fine, they resolve.)

- [ ] **Step 5: Lint + commit**

```bash
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/api/routes/ppe.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/api/routes/ppe.py tests/api/test_ppe_inventory_count_api.py
git add backend/app/api/routes/ppe.py tests/api/test_ppe_inventory_count_api.py
git commit -m "feat(p10-06): inventory routes — create + list + get(detail)"
```

---

### Task 9: Routes — patch lines + apply + cancel

**Files:**
- Modify: `backend/app/api/routes/ppe.py` (append after `get_inventory_count`)
- Test: `tests/api/test_ppe_inventory_count_api.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_ppe_inventory_count_api.py`:

```python
@pytest.mark.asyncio
async def test_patch_apply_flow_adjusts_stock(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id, batch_no="B-1", qty=10)

    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    line_id = created.json()["lines"][0]["id"]

    patched = await async_client.patch(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/lines",
        json={"entries": [{"line_id": line_id, "counted_qty": 7}]},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["lines"][0]["counted_qty"] == 7
    assert patched.json()["lines"][0]["delta"] == -3
    assert patched.json()["diff_count"] == 1

    applied = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/apply", headers=headers
    )
    assert applied.status_code == status.HTTP_200_OK
    assert applied.json()["status"] == "applied"

    # stock level now reflects the counted quantity
    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    total = next(l["total_quantity"] for l in levels.json()["items"] if l["item_id"] == item_id)
    assert total == 7


@pytest.mark.asyncio
async def test_apply_twice_returns_400(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    first = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/apply", headers=headers
    )
    assert first.status_code == status.HTTP_200_OK
    second = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/apply", headers=headers
    )
    assert second.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_patch_negative_counted_is_422(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    resp = await async_client.patch(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/lines",
        json={"entries": [{"line_id": "x", "counted_qty": -5}]},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_cancel_sets_status(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/ppe/stock/inventory/counts", json={}, headers=headers
    )
    count_id = created.json()["id"]
    cancelled = await async_client.post(
        f"/api/v1/ppe/stock/inventory/counts/{count_id}/cancel", headers=headers
    )
    assert cancelled.status_code == status.HTTP_200_OK
    assert cancelled.json()["status"] == "cancelled"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_ppe_inventory_count_api.py -k "patch_apply or apply_twice or negative or cancel" -q`
Expected: FAIL — 404/405 for the not-yet-registered `/lines`, `/apply`, `/cancel` routes.

- [ ] **Step 3: Add the three routes**

Append to `backend/app/api/routes/ppe.py` after `get_inventory_count` (still before `# --- 766н`):

```python
@router.patch(
    "/stock/inventory/counts/{count_id}/lines",
    response_model=PPEInventoryCountDetail,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("update", "ppe_inventory_count")
async def update_inventory_count_lines(
    count_id: str,
    payload: PPEInventoryCountLinesUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEInventoryCountDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    entries = [(entry.line_id, entry.counted_qty) for entry in payload.entries]
    try:
        await set_line_counts(
            session, tenant_id=tenant.id, count_id=count_id, entries=entries
        )
    except InventoryCountNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InventoryCountNotDraft as exc:
        raise _ppe_bad_request(str(exc)) from exc
    detail = await get_count_detail(session, tenant.id, count_id)
    return _inventory_count_detail(detail)


@router.post(
    "/stock/inventory/counts/{count_id}/apply",
    response_model=PPEInventoryCountDetail,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("update", "ppe_inventory_count")
async def apply_inventory_count(
    count_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEInventoryCountDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await apply_count(
            session,
            tenant_id=tenant.id,
            count_id=count_id,
            now=datetime.now(tz=timezone.utc),
        )
    except InventoryCountNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InventoryCountNotDraft as exc:
        raise _ppe_bad_request(str(exc)) from exc
    except InsufficientStockError as exc:
        raise _ppe_bad_request(str(exc)) from exc
    except StaleDataError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "inventory count was modified concurrently"
        ) from exc
    detail = await get_count_detail(session, tenant.id, count_id)
    return _inventory_count_detail(detail)


@router.post(
    "/stock/inventory/counts/{count_id}/cancel",
    response_model=PPEInventoryCountDetail,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("update", "ppe_inventory_count")
async def cancel_inventory_count(
    count_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEInventoryCountDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await cancel_count(session, tenant_id=tenant.id, count_id=count_id)
    except InventoryCountNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InventoryCountNotDraft as exc:
        raise _ppe_bad_request(str(exc)) from exc
    detail = await get_count_detail(session, tenant.id, count_id)
    return _inventory_count_detail(detail)
```

> `InsufficientStockError` is already imported (from `app.modules.ppe.stock`) and is caught defensively — it should not fire for a `>= 0` set-to-absolute adjustment, but mapping it to 400 keeps the contract consistent with `create_stock_movement`.

- [ ] **Step 4: Run the full API test file**

Run: `pytest tests/api/test_ppe_inventory_count_api.py -q`
Expected: PASS (8 tests).

- [ ] **Step 5: Backend regression + lint + commit**

```bash
pytest tests/unit/test_ppe_inventory_count_schema.py tests/api/test_ppe_inventory_count_service.py tests/api/test_ppe_inventory_count_api.py tests/api/test_ppe_stock_movements_service.py backend/tests/test_ppe_inventory_count_model.py backend/tests/test_wa06_ppe_inventory_count_migration.py -q
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/api/routes/ppe.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black backend/app/api/routes/ppe.py tests/api/test_ppe_inventory_count_api.py
git add backend/app/api/routes/ppe.py tests/api/test_ppe_inventory_count_api.py
git commit -m "feat(p10-06): inventory routes — patch lines + apply + cancel"
```

---

### Task 10: Frontend API client (`warehouse.ts`)

**Files:**
- Modify: `frontend/src/api/warehouse.ts`

- [ ] **Step 1: Add DTOs**

In `frontend/src/api/warehouse.ts`, after the `PPEStockShortageDto` type (line 54) and before the `PageResponse` type alias (line 56), add:

```ts
export type InventoryCountStatus = "draft" | "applied" | "cancelled";

export type InventoryCountLineDto = {
  id: string;
  batch_id: string;
  item_id: string;
  batch_no: string;
  location?: string | null;
  item_name: string;
  system_qty: number;
  counted_qty: number | null;
  on_hand: number;
  delta: number | null;
  adjustment_movement_id?: string | null;
};

export type InventoryCountDto = {
  id: string;
  status: InventoryCountStatus;
  scope_item_id?: string | null;
  scope_location?: string | null;
  note?: string | null;
  applied_at?: string | null;
  created_at: string;
  line_count: number;
  counted_count: number;
};

export type InventoryCountDetailDto = InventoryCountDto & {
  diff_count: number;
  lines: InventoryCountLineDto[];
};

export type CreateInventoryCountInput = {
  scope_item_id?: string | null;
  scope_location?: string | null;
  note?: string | null;
};

export type InventoryCountLineEntry = { line_id: string; counted_qty: number | null };
```

- [ ] **Step 2: Add methods**

In the `warehouseApi` object, add a comma after the `listShortages` method's closing `}` (line 83), then add these methods before the closing `};` (line 84):

```ts
  async listCounts(): Promise<InventoryCountDto[]> {
    const response = await apiClient.get<PageResponse<InventoryCountDto>>(
      "/ppe/stock/inventory/counts",
      { params: { limit: 50, offset: 0 } }
    );
    return response.data.items ?? [];
  },
  async createCount(input: CreateInventoryCountInput): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      "/ppe/stock/inventory/counts",
      input
    );
    return response.data;
  },
  async getCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.get<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}`
    );
    return response.data;
  },
  async patchCountLines(
    id: string,
    entries: InventoryCountLineEntry[]
  ): Promise<InventoryCountDetailDto> {
    const response = await apiClient.patch<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/lines`,
      { entries }
    );
    return response.data;
  },
  async applyCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/apply`,
      {}
    );
    return response.data;
  },
  async cancelCount(id: string): Promise<InventoryCountDetailDto> {
    const response = await apiClient.post<InventoryCountDetailDto>(
      `/ppe/stock/inventory/counts/${id}/cancel`,
      {}
    );
    return response.data;
  }
```

- [ ] **Step 3: Typecheck + commit**

Run: `npm --prefix frontend run typecheck`
Expected: exit 0.

```bash
git add frontend/src/api/warehouse.ts
git commit -m "feat(p10-06): warehouseApi inventory-count client methods + DTOs"
```

---

### Task 11: Frontend «Инвентаризация» section on `WarehousePage`

**Files:**
- Modify: `frontend/src/pages/warehouse/WarehousePage.tsx`

- [ ] **Step 1: Add imports + state**

In `frontend/src/pages/warehouse/WarehousePage.tsx`, extend the `@/api/warehouse` import (line 3-9) to add the DTO types:

```tsx
import {
  warehouseApi,
  type StockBatchDto,
  type StockLevelDto,
  type StockMovementDto,
  type PPEStockShortageDto,
  type InventoryCountDto,
  type InventoryCountDetailDto
} from "@/api/warehouse";
```

After the existing state hooks (after line 32, the `submitting` state), add:

```tsx
const [counts, setCounts] = useState<InventoryCountDto[]>([]);
const [activeCount, setActiveCount] = useState<InventoryCountDetailDto | null>(null);
const [countForm, setCountForm] = useState({ scope_item_id: "", scope_location: "", note: "" });
const [countedInputs, setCountedInputs] = useState<Record<string, string>>({});
```

- [ ] **Step 2: Wire the count list into `load` + add handlers**

In the `load` function's `Promise.all` (lines 38-43), add `warehouseApi.listCounts()` as a 5th call and set it:

```tsx
    const [levelsData, batchesData, movementsData, shortagesData, countsData] = await Promise.all([
      warehouseApi.listLevels(),
      warehouseApi.listBatches(),
      warehouseApi.listMovements(),
      warehouseApi.listShortages(),
      warehouseApi.listCounts()
    ]);
    setLevels(levelsData);
    setBatches(batchesData);
    setMovements(movementsData);
    setShortages(shortagesData);
    setCounts(countsData);
```

After the `submitMovement` handler (line 72), add the inventory handlers:

```tsx
const createCount = async () => {
  setSubmitting(true);
  try {
    const detail = await warehouseApi.createCount({
      scope_item_id: countForm.scope_item_id || null,
      scope_location: countForm.scope_location || null,
      note: countForm.note || null
    });
    setCountForm({ scope_item_id: "", scope_location: "", note: "" });
    openCountDetail(detail);
    await load();
  } catch (err) {
    setError((err as ApiError) ?? { message: "Не удалось создать инвентаризацию" });
  } finally {
    setSubmitting(false);
  }
};

const openCountDetail = (detail: InventoryCountDetailDto) => {
  setActiveCount(detail);
  const seeded: Record<string, string> = {};
  detail.lines.forEach((line) => {
    seeded[line.id] = line.counted_qty === null ? "" : String(line.counted_qty);
  });
  setCountedInputs(seeded);
};

const openCount = async (id: string) => {
  try {
    openCountDetail(await warehouseApi.getCount(id));
  } catch (err) {
    setError((err as ApiError) ?? { message: "Не удалось открыть инвентаризацию" });
  }
};

const saveCounts = async () => {
  if (!activeCount) return;
  setSubmitting(true);
  try {
    const entries = activeCount.lines.map((line) => ({
      line_id: line.id,
      counted_qty: countedInputs[line.id] === "" || countedInputs[line.id] === undefined
        ? null
        : Number(countedInputs[line.id])
    }));
    openCountDetail(await warehouseApi.patchCountLines(activeCount.id, entries));
  } catch (err) {
    setError((err as ApiError) ?? { message: "Не удалось сохранить факт" });
  } finally {
    setSubmitting(false);
  }
};

const applyActiveCount = async () => {
  if (!activeCount) return;
  setSubmitting(true);
  try {
    openCountDetail(await warehouseApi.applyCount(activeCount.id));
    await load();
  } catch (err) {
    setError((err as ApiError) ?? { message: "Не удалось применить инвентаризацию" });
  } finally {
    setSubmitting(false);
  }
};

const cancelActiveCount = async () => {
  if (!activeCount) return;
  setSubmitting(true);
  try {
    openCountDetail(await warehouseApi.cancelCount(activeCount.id));
    await load();
  } catch (err) {
    setError((err as ApiError) ?? { message: "Не удалось отменить инвентаризацию" });
  } finally {
    setSubmitting(false);
  }
};
```

- [ ] **Step 3: Add the section JSX**

Insert this `<Card>` between the Дефицит card's closing `</Card>` (line 293) and the wrapper `</div>` (line 294):

```tsx
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            Инвентаризация
            <Badge variant="secondary">{counts.length}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2 items-end">
            <Input
              placeholder="ID позиции (опц.)"
              value={countForm.scope_item_id}
              onChange={(e) => setCountForm({ ...countForm, scope_item_id: e.target.value })}
            />
            <Input
              placeholder="Локация (опц.)"
              value={countForm.scope_location}
              onChange={(e) => setCountForm({ ...countForm, scope_location: e.target.value })}
            />
            <Input
              placeholder="Заметка (опц.)"
              value={countForm.note}
              onChange={(e) => setCountForm({ ...countForm, note: e.target.value })}
            />
            <Button onClick={createCount} disabled={submitting}>
              Создать
            </Button>
          </div>

          {counts.length === 0 ? (
            <EmptyState title="Нет инвентаризаций" description="Создайте срез для сверки факта." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Статус</TableHead>
                  <TableHead>Заметка</TableHead>
                  <TableHead>Строк</TableHead>
                  <TableHead>Сосчитано</TableHead>
                  <TableHead>Создан</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {counts.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>
                      <Badge variant={c.status === "applied" ? "secondary" : "outline"}>
                        {c.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{c.note || "—"}</TableCell>
                    <TableCell>{c.line_count}</TableCell>
                    <TableCell>{c.counted_count}</TableCell>
                    <TableCell>{formatDate(c.created_at) || "—"}</TableCell>
                    <TableCell>
                      <Button variant="outline" onClick={() => openCount(c.id)}>
                        Открыть
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}

          {activeCount ? (
            <div className="space-y-3 border-t pt-3">
              <div className="flex items-center gap-2">
                <span className="font-medium">Строки инвентаризации</span>
                <Badge variant="outline">{activeCount.status}</Badge>
                <Badge variant="secondary">расхождений: {activeCount.diff_count}</Badge>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Партия</TableHead>
                    <TableHead>Локация</TableHead>
                    <TableHead>Система</TableHead>
                    <TableHead>Остаток</TableHead>
                    <TableHead>Факт</TableHead>
                    <TableHead>Δ</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeCount.lines.map((line) => (
                    <TableRow key={line.id}>
                      <TableCell className="font-medium">{line.batch_no}</TableCell>
                      <TableCell>{line.location || "—"}</TableCell>
                      <TableCell>{line.system_qty}</TableCell>
                      <TableCell>{line.on_hand}</TableCell>
                      <TableCell>
                        <Input
                          aria-label={`Факт ${line.batch_no}`}
                          value={countedInputs[line.id] ?? ""}
                          disabled={activeCount.status !== "draft"}
                          onChange={(e) =>
                            setCountedInputs({ ...countedInputs, [line.id]: e.target.value })
                          }
                        />
                      </TableCell>
                      <TableCell>{line.delta === null ? "—" : line.delta}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {activeCount.status === "draft" ? (
                <div className="flex gap-2">
                  <Button variant="outline" onClick={saveCounts} disabled={submitting}>
                    Сохранить факт
                  </Button>
                  <Button onClick={applyActiveCount} disabled={submitting}>
                    Применить
                  </Button>
                  <Button variant="ghost" onClick={cancelActiveCount} disabled={submitting}>
                    Отменить
                  </Button>
                </div>
              ) : null}
            </div>
          ) : null}
        </CardContent>
      </Card>
```

> If `Badge` has no `"outline"` variant in `@/components/ui`, use `"secondary"` instead — check `frontend/src/components/ui/badge.tsx` for the allowed variants before finalizing.

- [ ] **Step 4: Typecheck + build**

Run: `npm --prefix frontend run typecheck`
Expected: exit 0.
Run: `npm --prefix frontend run build`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/warehouse/WarehousePage.tsx
git commit -m "feat(p10-06): WarehousePage «Инвентаризация» section (list + create + count grid + apply/cancel)"
```

---

### Task 12: Frontend vitest for the section

**Files:**
- Modify: `frontend/src/__tests__/WarehousePage.test.tsx`

- [ ] **Step 1: Extend the mock + write the failing test**

In `frontend/src/__tests__/WarehousePage.test.tsx`, add the new mock fns after `listShortagesMock` (line 11):

```tsx
const listCountsMock = vi.fn();
const createCountMock = vi.fn();
const getCountMock = vi.fn();
const patchCountLinesMock = vi.fn();
const applyCountMock = vi.fn();
const cancelCountMock = vi.fn();
```

Add them to the `vi.mock("@/api/warehouse", ...)` `warehouseApi` object (after `listShortages`, line 18):

```tsx
    listCounts: (...args: unknown[]) => listCountsMock(...args),
    createCount: (...args: unknown[]) => createCountMock(...args),
    getCount: (...args: unknown[]) => getCountMock(...args),
    patchCountLines: (...args: unknown[]) => patchCountLinesMock(...args),
    applyCount: (...args: unknown[]) => applyCountMock(...args),
    cancelCount: (...args: unknown[]) => cancelCountMock(...args)
```

In `beforeEach` (lines 24-32), reset + default the counts list so `Promise.all` resolves:

```tsx
  listCountsMock.mockReset();
  createCountMock.mockReset();
  getCountMock.mockReset();
  patchCountLinesMock.mockReset();
  applyCountMock.mockReset();
  cancelCountMock.mockReset();
  listCountsMock.mockResolvedValue([]);
```

Add these tests before the closing `});` of the `describe` (line 113):

```tsx
  it("renders the inventory section with an existing count", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listCountsMock.mockResolvedValue([
      {
        id: "c1", status: "draft", scope_item_id: null, scope_location: null,
        note: "июль", applied_at: null, created_at: "2026-07-03T00:00:00Z",
        line_count: 2, counted_count: 0
      }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Инвентаризация")).toBeInTheDocument());
    expect(screen.getByText("июль")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Открыть" })).toBeInTheDocument();
  });

  it("creates a count and shows its lines", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listCountsMock.mockResolvedValue([]);
    createCountMock.mockResolvedValue({
      id: "c9", status: "draft", scope_item_id: null, scope_location: null,
      note: null, applied_at: null, created_at: "2026-07-03T00:00:00Z",
      line_count: 1, counted_count: 0, diff_count: 0,
      lines: [
        {
          id: "l1", batch_id: "b1", item_id: "i1", batch_no: "B-1", location: null,
          item_name: "Каска", system_qty: 10, counted_qty: null, on_hand: 10,
          delta: null, adjustment_movement_id: null
        }
      ]
    });

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Инвентаризация")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Создать" }));

    await waitFor(() => expect(createCountMock).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("B-1")).toBeInTheDocument());
  });
```

- [ ] **Step 2: Run test to verify it fails then passes**

Run: `npm --prefix frontend run test -- WarehousePage`
Expected: initially the new tests FAIL if the section isn't present; since Task 11 added the section, they should PASS. If Task 11 and 12 are done together, run once and expect PASS. (If red, fix per the failure — likely a button label or text mismatch with Task 11's JSX.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/WarehousePage.test.tsx
git commit -m "test(p10-06): vitest for WarehousePage «Инвентаризация» section"
```

---

### Task 13: Docs, OpenAPI baseline, gates, handoff

**Files:**
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (P10-06 row)
- Modify: `CHANGELOG.md`
- Modify: `docs/stabilization/openapi_routes_baseline.json` (regenerated)
- Modify: `AI_IMPLEMENTATION_REPORT.md` (new handoff at top)

- [ ] **Step 1: Regenerate the OpenAPI baseline**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe scripts/ci/check_openapi_snapshot.py --snapshot`
Then verify it is now clean:
Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe scripts/ci/check_openapi_snapshot.py --compare`
Expected: exit 0 (baseline matches). The diff should be purely additive: **+6 routes** (`POST /api/v1/ppe/stock/inventory/counts`, `GET /api/v1/ppe/stock/inventory/counts`, `GET /api/v1/ppe/stock/inventory/counts/{count_id}`, `PATCH /api/v1/ppe/stock/inventory/counts/{count_id}/lines`, `POST .../apply`, `POST .../cancel`) + the new inventory schemas. Record the new route/schema counts (was 811/653) for the handoff.

- [ ] **Step 2: Update the roadmap row**

In `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, the P10-06 row (the `| **P10-06** | СИЗ склад (полный) | ...` line): append the inventory shipped-prose and **remove «инвентаризация» from the «Остаётся» list**. Change the status label tail and set the remaining list to: `**Остаётся:** перемещения, поставщики, бюджет безопасности, мобильная выдача`. Add to the shipped prose: `+ инвентаризация (двухфазный срез ppe_inventory_count → adjustment-проводки, миграция wa06, GET/POST /ppe/stock/inventory/counts + apply/cancel, фронт-секция «Инвентаризация»)`.

- [ ] **Step 3: Add a CHANGELOG entry**

Prepend a dated entry to `CHANGELOG.md` (match the existing format for 2026-07-03 entries):

```markdown
### 2026-07-03 — P10-06 СИЗ склад: инвентаризация (сверка факт↔система)

- Двухфазная инвентаризация (`ppe_inventory_count` + `ppe_inventory_count_line`, миграция `wa06`):
  черновик со снимком партий → ввод факта → `apply` выпускает `adjustment`-проводки через
  `record_movement` (честный остаток, чокпоинт цел). Опц. фильтр item/location, несосчитанные
  строки пропускаются, дельта считается от живого остатка.
- Эндпоинты `POST/GET /ppe/stock/inventory/counts`, `GET /…/{id}`, `PATCH /…/{id}/lines`,
  `POST /…/{id}/apply`, `POST /…/{id}/cancel` (за флагом `warehouse`). Фронт-секция «Инвентаризация»
  на `WarehousePage`. OpenAPI baseline пере-снят (additive).
```

- [ ] **Step 4: Full backend regression on the slice + frontend gates**

```bash
pytest backend/tests/test_ppe_inventory_count_model.py backend/tests/test_wa06_ppe_inventory_count_migration.py tests/unit/test_ppe_inventory_count_schema.py tests/api/test_ppe_inventory_count_service.py tests/api/test_ppe_inventory_count_api.py tests/api/test_ppe_stock_movements_service.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_shortage_service.py tests/api/test_ppe_warehouse_api.py -q
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/modules/ppe/inventory.py backend/app/api/routes/ppe.py backend/app/models/ppe.py backend/app/schemas/ppe.py
C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black --check backend/app/modules/ppe/inventory.py backend/app/api/routes/ppe.py backend/app/models/ppe.py backend/app/schemas/ppe.py
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
```

Expected: all green. Note the local Python-3.13 vs canon-3.12.12 mismatch in your output.

> **PG16 gate (migration validation):** the `wa06` migration is only validated by `scripts/ci/local_gate.py --db-only` (needs local PG16 + Docker). If unavailable in this environment, note it as **deferred to CI** — do not block. Do NOT run the full `make cs:test` suite.

- [ ] **Step 5: Write the handoff + commit docs**

Prepend a `## Last Agent Handoff (2026-07-03, P10-06 СИЗ СКЛАД — ИНВЕНТАРИЗАЦИЯ)` block to the top of `AI_IMPLEMENTATION_REPORT.md` summarizing: the two-table `wa06` migration, the `inventory.py` service (create/set/detail/list/apply/cancel), the additive `record_movement` ref, the 6 routes, the frontend section, the OpenAPI re-snap counts, verification results, and the **Next** step (следующий срез P10-06 — поставщики или перемещения). Then:

```bash
git add docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md CHANGELOG.md docs/stabilization/openapi_routes_baseline.json AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(p10-06): roadmap + changelog + OpenAPI baseline + handoff for inventory count"
```

---

## Self-Review (author checklist — completed)

**Spec coverage:** every spec layer maps to a task — models (T1), migration wa06 (T2), record_movement ref (T3, Слой 4), service create/set/apply/cancel/detail/list (T4-T6, Слой 3), schemas (T7, Слой 5), routes ×6 (T8-T9, Слой 6), frontend api+section (T10-T12, Слой 7), docs/OpenAPI/roadmap/changelog/handoff (T13). Error-handling table (spec §Обработка ошибок): 404 flag-off + cross-tenant (T8), 400 not-draft (T9), 422 negative (T9), 409 concurrent (route catch, T9). `diff_count` moved from Read→Detail (list stays O(1); noted as a deliberate refinement over the spec).

**Placeholder scan:** no TBD/TODO; every code/test step shows full code. The one awkward query snippet in T6 Step 1 is called out with a verbatim replacement.

**Type consistency:** service returns `CountDetailView`/`CountSummaryView`/`CountLineView` (T4-T5) consumed verbatim by `_inventory_count_detail`/`_inventory_count_read` (T8). Schema field names (`system_qty`, `counted_qty`, `on_hand`, `delta`, `line_count`, `counted_count`, `diff_count`) identical across service views, schemas (T7), routes (T8-T9), and frontend DTOs (T10). `record_movement(..., ref_type=, ref_id=)` added in T3 and called in T6. `KIND_ADJUSTMENT` imported from `stock.py` (exists). `status` query param aliased to avoid shadowing the `fastapi.status` module (T8).
