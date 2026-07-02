# PPE Stock Movements Ledger (honest остатки) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make PPE warehouse stock honest — introduce an append-only `ppe_stock_movement` journal, mutate `PPEStockBatch.quantity` only through a movement-recording service, and deplete stock (FIFO) when PPE is issued to a worker.

**Architecture:** Approach B — `batch.quantity` is the live cached balance; `ppe_stock_movement` is the immutable journal. Both change in one transaction via one service (`modules/ppe/stock.py`). Issuance depletion is wired at the **route** layer (next to the existing outbox enqueue), keeping the pure `issue_ppe_item` service free of warehouse coupling. FIFO allocation auto-picks oldest batches (`received_at` nulls-last, `id` tiebreaker) unless an explicit `batch_id` is passed. Insufficient stock → 400; warehouse flag off or item has no batches → no movement (backward compatible). Additive migration `wa04`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy (async) / Alembic; React 18 / TypeScript / Vite / vitest. Spec: `docs/superpowers/specs/2026-07-02-p10-06-ppe-stock-movements-design.md`.

---

## Environment notes (read once)

- Backend venv is in the **main repo copy**: `D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\.venv` (Py3.13). From this worktree call it by absolute path, e.g. `& "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\.venv\Scripts\python.exe" -m pytest ...`. Canonical Py3.12.12 runs on the PG gate.
- Backend tests run from repo root (pytest `pythonpath = ["backend", "."]`). Test IDs like `tests/api/test_ppe_stock_movements_api.py::test_...`.
- **Alembic never runs on SQLite** (initial schema is JSONB). The `wa04` migration is validated **only** by the PG16 gate: `python scripts/ci/local_gate.py --db-only` (Docker + PG16). Unit/API tests use `metadata.create_all`, so the **ORM model** (not the migration) is what those tests exercise.
- Feature `warehouse` is **default-ON** (`is_feature_enabled(..., default=True)`), so "flag off" only happens with an explicit `FeatureEnablement(on=False)` row. The main backward-compat guard is "item has no batches → no movement."
- After any schema/route change, the OpenAPI snapshot guard will fail until re-snapped (Task 10).

## File Structure

| File | Create/Modify | Responsibility |
|---|---|---|
| `backend/app/models/ppe.py` | Modify | Add `PPEStockMovement` ORM model (after `PPEStockBatch`) |
| `backend/app/models/models.py` | Modify | Re-export `PPEStockMovement` (import + `__all__`) |
| `backend/app/models/ppe_registry.py` | Modify | Re-export `PPEStockMovement` |
| `backend/app/migrations/versions/20260702_wa04_ppe_stock_movement.py` | Create | Additive migration for `ppe_stock_movement` |
| `backend/app/modules/ppe/stock.py` | Create | Pure `allocate_fifo` + `record_movement`/`deplete_for_issue` service + errors + kind constants |
| `backend/app/modules/ppe/__init__.py` | Modify | Export stock service symbols |
| `backend/app/schemas/ppe.py` | Modify | Movement schemas; add `batch_id` to issue/replace; drop `quantity` from batch-update |
| `backend/app/api/routes/ppe.py` | Modify | `POST/GET /stock/movements`; opening-receipt on batch create; wire depletion into issue/replace |
| `backend/tests/test_wa04_ppe_stock_movement_migration.py` | Create | Pin model shape + migration shape |
| `tests/unit/test_ppe_stock_allocation.py` | Create | Pure `allocate_fifo` unit tests |
| `tests/api/test_ppe_stock_movements_service.py` | Create | DB service tests (`record_movement`, `deplete_for_issue`) |
| `tests/api/test_ppe_stock_movements_api.py` | Create | Movements endpoints + issue-depletion contract |
| `tests/api/test_ppe_warehouse_api.py` | Modify | Fix `test_create_list_get_patch_batch` (PATCH no longer accepts `quantity`) |
| `frontend/src/api/warehouse.ts` | Modify | `StockMovementDto`, `listMovements`, `createMovement` |
| `frontend/src/pages/warehouse/WarehousePage.tsx` | Modify | "Движения" section + manual receipt/adjustment form |
| `frontend/src/__tests__/WarehousePage.test.tsx` | Modify | Extend mock (listMovements/createMovement) + movement render test |
| `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` | Modify | P10-06 status: skeleton → +movements ledger |
| `AI_IMPLEMENTATION_REPORT.md` | Modify | Handoff entry |
| `docs/stabilization/openapi_baseline.json` (or as guard reports) | Modify | Re-snapped baseline |

---

### Task 1: `PPEStockMovement` ORM model + re-exports

**Files:**
- Modify: `backend/app/models/ppe.py` (add class after `PPEStockBatch`, ends line 158)
- Modify: `backend/app/models/models.py` (import block ~line 208-214; `__all__` ~line 586-592)
- Modify: `backend/app/models/ppe_registry.py`
- Test: `backend/tests/test_wa04_ppe_stock_movement_migration.py` (model half)

- [ ] **Step 1: Write the failing model-shape test**

Create `backend/tests/test_wa04_ppe_stock_movement_migration.py`:

```python
"""Pin: PPEStockMovement model + ppe_stock_movement migration shape (P10-06)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260702_wa04_ppe_stock_movement.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa04_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_ppe_stock_movement_model_table_and_columns() -> None:
    from app.models.models import PPEStockMovement

    assert PPEStockMovement.__tablename__ == "ppe_stock_movement"
    cols = set(PPEStockMovement.__table__.columns.keys())
    assert {
        "id",
        "tenant_id",
        "version",
        "created_at",
        "updated_at",
        "item_id",
        "batch_id",
        "kind",
        "quantity_delta",
        "occurred_at",
        "reason",
        "ref_type",
        "ref_id",
    } <= cols
    # append-only journal: no soft-delete column
    assert "deleted_at" not in cols


def test_ppe_stock_movement_reexported_from_registry() -> None:
    from app.models.ppe_registry import PPEStockMovement  # noqa: F401


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260702_wa04_ppe_stock_movement"
    assert mod.down_revision == "20260702_br01_branch_entity"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "ppe_stock_movement"' in src
    assert 'op.drop_table("ppe_stock_movement")' in src
```

- [ ] **Step 2: Run the model test to verify it fails**

Run: `& "D:\Кодинг\3. Создание платформы по ОТ\Создание платформы по ОТ\.venv\Scripts\python.exe" -m pytest backend/tests/test_wa04_ppe_stock_movement_migration.py::test_ppe_stock_movement_model_table_and_columns -q`
Expected: FAIL — `ImportError: cannot import name 'PPEStockMovement'`.

- [ ] **Step 3: Add the model**

In `backend/app/models/ppe.py`, immediately after the `PPEStockBatch` class (after its `__table_args__`, line 158), add:

```python
class PPEStockMovement(TenantBaseModel):
    """Append-only stock ledger (P10-06). ``batch.quantity`` is the live cached
    balance; each row here is the immutable journal entry that changed it.
    ``ref_type``/``ref_id`` are plain strings (no FK) so the journal survives a
    hard-delete of the source issue — same convention as ``replaces_issue_id``.
    ``kind`` is VARCHAR, not a PG enum (enum-parity convention)."""

    __tablename__ = "ppe_stock_movement"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppe_stock_batch.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(tz=timezone.utc),
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ref_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ref_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_ppe_stock_movement_item", "tenant_id", "item_id"),
        Index("ix_ppe_stock_movement_batch", "tenant_id", "batch_id"),
    )
```

- [ ] **Step 4: Add the re-exports**

In `backend/app/models/models.py`, add `PPEStockMovement` to the PPE import block (alphabetically near `PPEStockBatch`, ~line 212) and to `__all__` (~line 590, next to `"PPEStockBatch",`):

```python
    PPEStockBatch,
    PPEStockMovement,
```
and
```python
    "PPEStockBatch",
    "PPEStockMovement",
```

In `backend/app/models/ppe_registry.py`, add to both the import and `__all__`:

```python
from app.models.models import (
    PPEIssue,
    PPEIssueStatus,
    PPEItem,
    PPEItemCategory,
    PPEStockBatch,
    PPEStockMovement,
)

__all__ = [
    "PPEItem",
    "PPEItemCategory",
    "PPEIssue",
    "PPEIssueStatus",
    "PPEStockBatch",
    "PPEStockMovement",
]
```

- [ ] **Step 5: Run the model + registry tests to verify they pass**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest backend/tests/test_wa04_ppe_stock_movement_migration.py::test_ppe_stock_movement_model_table_and_columns backend/tests/test_wa04_ppe_stock_movement_migration.py::test_ppe_stock_movement_reexported_from_registry -q`
Expected: 2 passed. (The two migration-metadata tests still fail — the migration file lands in Task 2.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/ppe.py backend/app/models/models.py backend/app/models/ppe_registry.py backend/tests/test_wa04_ppe_stock_movement_migration.py
git commit -m "feat(p10-06): PPEStockMovement ORM model + re-exports"
```

---

### Task 2: Additive migration `wa04`

**Files:**
- Create: `backend/app/migrations/versions/20260702_wa04_ppe_stock_movement.py`
- Test: `backend/tests/test_wa04_ppe_stock_movement_migration.py` (migration half, already written in Task 1)

- [ ] **Step 1: Run the migration-metadata tests to verify they fail**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest backend/tests/test_wa04_ppe_stock_movement_migration.py::test_migration_revision_metadata -q`
Expected: FAIL — file not found / import error on the migration path.

- [ ] **Step 2: Write the migration**

Create `backend/app/migrations/versions/20260702_wa04_ppe_stock_movement.py`:

```python
"""ppe stock movement ledger (P10-06 / honest остатки / vNext §12.3)

Additive: creates ppe_stock_movement (append-only journal of stock deltas).
No column added to existing tables; no data backfill (existing ppe_stock_batch
rows keep their quantity as the opening balance). ``kind`` is VARCHAR, not a PG
enum (enum-parity convention). Chains off the branch-entity head (br01).

Revision ID: 20260702_wa04_ppe_stock_movement
Revises: 20260702_br01_branch_entity
Create Date: 2026-07-02 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260702_wa04_ppe_stock_movement"
down_revision = "20260702_br01_branch_entity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_stock_movement",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("batch_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=True),
        sa.Column("ref_type", sa.String(length=64), nullable=True),
        sa.Column("ref_id", sa.String(length=36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["ppeitem.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["ppe_stock_batch.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ppe_stock_movement_tenant_id"), "ppe_stock_movement", ["tenant_id"]
    )
    op.create_index(
        "ix_ppe_stock_movement_item", "ppe_stock_movement", ["tenant_id", "item_id"]
    )
    op.create_index(
        "ix_ppe_stock_movement_batch", "ppe_stock_movement", ["tenant_id", "batch_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ppe_stock_movement_batch", table_name="ppe_stock_movement")
    op.drop_index("ix_ppe_stock_movement_item", table_name="ppe_stock_movement")
    op.drop_index(op.f("ix_ppe_stock_movement_tenant_id"), table_name="ppe_stock_movement")
    op.drop_table("ppe_stock_movement")
```

- [ ] **Step 3: Run the full migration-shape test file to verify it passes**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest backend/tests/test_wa04_ppe_stock_movement_migration.py -q`
Expected: 4 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/migrations/versions/20260702_wa04_ppe_stock_movement.py
git commit -m "feat(p10-06): additive migration wa04 for ppe_stock_movement"
```

> **Note:** `alembic upgrade heads` on PG16 is validated later by the gate (Task 10). Do **not** try to run alembic on SQLite.

---

### Task 3: Pure FIFO allocator + errors + kind constants

**Files:**
- Create: `backend/app/modules/ppe/stock.py`
- Test: `tests/unit/test_ppe_stock_allocation.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/unit/test_ppe_stock_allocation.py`:

```python
"""Pure FIFO allocation for the PPE stock ledger (P10-06)."""
from __future__ import annotations

import pytest

from app.modules.ppe.stock import Allocation, InsufficientStockError, allocate_fifo


def test_allocate_single_batch_partial() -> None:
    assert allocate_fifo([("b1", 10)], 4) == [Allocation(batch_id="b1", taken=4)]


def test_allocate_exact_single_batch() -> None:
    assert allocate_fifo([("b1", 5)], 5) == [Allocation(batch_id="b1", taken=5)]


def test_allocate_spans_multiple_batches_oldest_first() -> None:
    # caller passes batches already ordered oldest-first
    result = allocate_fifo([("b1", 3), ("b2", 10)], 7)
    assert result == [Allocation("b1", 3), Allocation("b2", 4)]


def test_allocate_skips_empty_batches() -> None:
    result = allocate_fifo([("b1", 0), ("b2", 5)], 5)
    assert result == [Allocation("b2", 5)]


def test_allocate_insufficient_raises_with_available() -> None:
    with pytest.raises(InsufficientStockError) as exc:
        allocate_fifo([("b1", 2), ("b2", 1)], 5)
    assert exc.value.requested == 5
    assert exc.value.available == 3


def test_allocate_zero_quantity_is_noop() -> None:
    assert allocate_fifo([("b1", 5)], 0) == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/unit/test_ppe_stock_allocation.py -q`
Expected: FAIL — `ModuleNotFoundError: app.modules.ppe.stock`.

- [ ] **Step 3: Write the pure allocator + shared symbols**

Create `backend/app/modules/ppe/stock.py`:

```python
"""PPE warehouse stock ledger (P10-06, Approach B).

``batch.quantity`` is the live cached balance; every change to it is recorded as
an immutable ``PPEStockMovement`` in the same transaction. FIFO allocation and
movement recording are the only sanctioned way to mutate stock quantity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.feature_flags import is_feature_enabled
from app.models.ppe_registry import PPEStockBatch, PPEStockMovement

KIND_RECEIPT = "receipt"
KIND_ISSUE = "issue"
KIND_WRITEOFF = "writeoff"
KIND_ADJUSTMENT = "adjustment"
MANUAL_KINDS = frozenset({KIND_RECEIPT, KIND_WRITEOFF, KIND_ADJUSTMENT})
WAREHOUSE_FEATURE_CODE = "warehouse"


class InsufficientStockError(Exception):
    """Raised when a depletion would drive on-hand below zero."""

    def __init__(self, requested: int, available: int) -> None:
        super().__init__(
            f"insufficient stock: requested {requested}, available {available}"
        )
        self.requested = requested
        self.available = available


class StockBatchNotFound(Exception):
    """Raised when a referenced batch does not exist for the tenant/item."""

    def __init__(self, batch_id: str) -> None:
        super().__init__(f"PPE stock batch not found: {batch_id}")
        self.batch_id = batch_id


@dataclass(slots=True, frozen=True)
class Allocation:
    batch_id: str
    taken: int


def allocate_fifo(available: list[tuple[str, int]], quantity: int) -> list[Allocation]:
    """Allocate ``quantity`` across ``available`` (id, on_hand) pairs, oldest-first.

    ``available`` MUST already be ordered oldest-first by the caller. Raises
    :class:`InsufficientStockError` when the total on-hand is short.
    """
    if quantity <= 0:
        return []
    remaining = quantity
    result: list[Allocation] = []
    for batch_id, on_hand in available:
        if remaining <= 0:
            break
        if on_hand <= 0:
            continue
        take = min(on_hand, remaining)
        result.append(Allocation(batch_id=batch_id, taken=take))
        remaining -= take
    if remaining > 0:
        raise InsufficientStockError(requested=quantity, available=quantity - remaining)
    return result
```

- [ ] **Step 4: Run to verify it passes**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/unit/test_ppe_stock_allocation.py -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/stock.py tests/unit/test_ppe_stock_allocation.py
git commit -m "feat(p10-06): pure FIFO allocator + stock ledger errors/constants"
```

---

### Task 4: `record_movement` DB service (manual receipt/writeoff/adjustment)

**Files:**
- Modify: `backend/app/modules/ppe/stock.py`
- Modify: `backend/app/modules/ppe/__init__.py`
- Test: `tests/api/test_ppe_stock_movements_service.py`

- [ ] **Step 1: Write the failing service tests**

Create `tests/api/test_ppe_stock_movements_service.py`:

```python
"""DB-level tests for the PPE stock ledger service (P10-06)."""
from __future__ import annotations

import pytest

from app.models.ppe_registry import PPEItem, PPEStockBatch, PPEStockMovement
from app.modules.ppe.stock import (
    InsufficientStockError,
    StockBatchNotFound,
    record_movement,
)
from tests.utils.factories import TestDataFactory


async def _item_and_batch(session, tenant_id: str, *, qty: int):
    item = PPEItem(tenant_id=tenant_id, name="Каска")
    session.add(item)
    await session.flush()
    batch = PPEStockBatch(tenant_id=tenant_id, item_id=item.id, batch_no="B-1", quantity=qty)
    session.add(batch)
    await session.flush()
    return item, batch


@pytest.mark.asyncio
async def test_receipt_increases_balance_and_writes_journal(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)

        movement = await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="receipt", quantity=5
        )
        await session.refresh(batch)

    assert batch.quantity == 15
    assert movement.quantity_delta == 5
    assert movement.kind == "receipt"
    assert movement.item_id == batch.item_id


@pytest.mark.asyncio
async def test_writeoff_decreases_balance(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)
        movement = await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="writeoff", quantity=4
        )
        await session.refresh(batch)
    assert batch.quantity == 6
    assert movement.quantity_delta == -4


@pytest.mark.asyncio
async def test_adjustment_sets_absolute_balance(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=10)
        movement = await record_movement(
            session, tenant_id=tenant.id, batch_id=batch.id, kind="adjustment", quantity=7
        )
        await session.refresh(batch)
    assert batch.quantity == 7
    assert movement.quantity_delta == -3  # 7 - 10


@pytest.mark.asyncio
async def test_writeoff_below_zero_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, batch = await _item_and_batch(session, tenant.id, qty=3)
        with pytest.raises(InsufficientStockError):
            await record_movement(
                session, tenant_id=tenant.id, batch_id=batch.id, kind="writeoff", quantity=5
            )


@pytest.mark.asyncio
async def test_unknown_batch_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        with pytest.raises(StockBatchNotFound):
            await record_movement(
                session, tenant_id=tenant.id, batch_id="nope", kind="receipt", quantity=1
            )
```

- [ ] **Step 2: Run to verify it fails**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_service.py -q`
Expected: FAIL — `ImportError: cannot import name 'record_movement'`.

- [ ] **Step 3: Add `_load_batch`, `_write_movement`, `record_movement` to `stock.py`**

Append to `backend/app/modules/ppe/stock.py`:

```python
async def _load_batch(
    session: AsyncSession,
    tenant_id: str,
    batch_id: str,
    *,
    item_id: str | None = None,
) -> PPEStockBatch:
    stmt = select(PPEStockBatch).where(
        PPEStockBatch.id == batch_id,
        PPEStockBatch.tenant_id == tenant_id,
        PPEStockBatch.deleted_at.is_(None),
    )
    if item_id is not None:
        stmt = stmt.where(PPEStockBatch.item_id == item_id)
    batch = (await session.execute(stmt)).scalar_one_or_none()
    if batch is None:
        raise StockBatchNotFound(batch_id)
    return batch


async def _write_movement(
    session: AsyncSession,
    *,
    tenant_id: str,
    batch: PPEStockBatch,
    kind: str,
    delta: int,
    reason: str | None = None,
    occurred_at: datetime | None = None,
    ref_type: str | None = None,
    ref_id: str | None = None,
) -> PPEStockMovement:
    """Apply ``delta`` to the batch balance and append the journal row.

    The ONLY place ``batch.quantity`` is mutated. Guards on-hand >= 0.
    """
    new_qty = batch.quantity + delta
    if new_qty < 0:
        raise InsufficientStockError(requested=-delta, available=batch.quantity)
    batch.quantity = new_qty
    movement = PPEStockMovement(
        tenant_id=tenant_id,
        item_id=batch.item_id,
        batch_id=batch.id,
        kind=kind,
        quantity_delta=delta,
        occurred_at=occurred_at or datetime.now(tz=timezone.utc),
        reason=reason,
        ref_type=ref_type,
        ref_id=ref_id,
    )
    session.add(movement)
    await session.flush()
    await session.refresh(movement)
    return movement


async def record_movement(
    session: AsyncSession,
    *,
    tenant_id: str,
    batch_id: str,
    kind: str,
    quantity: int,
    reason: str | None = None,
    occurred_at: datetime | None = None,
) -> PPEStockMovement:
    """Manual receipt / writeoff / adjustment against one batch.

    - receipt: +quantity   (quantity must be > 0)
    - writeoff: -quantity   (quantity must be > 0)
    - adjustment: set the batch to an absolute ``quantity`` (>= 0)
    """
    if kind not in MANUAL_KINDS:
        raise ValueError(f"unsupported manual movement kind: {kind}")
    batch = await _load_batch(session, tenant_id, batch_id)
    if kind == KIND_RECEIPT:
        if quantity <= 0:
            raise ValueError("receipt quantity must be positive")
        delta = quantity
    elif kind == KIND_WRITEOFF:
        if quantity <= 0:
            raise ValueError("writeoff quantity must be positive")
        delta = -quantity
    else:  # KIND_ADJUSTMENT — set-to absolute
        delta = quantity - batch.quantity
    return await _write_movement(
        session,
        tenant_id=tenant_id,
        batch=batch,
        kind=kind,
        delta=delta,
        reason=reason,
        occurred_at=occurred_at,
    )
```

- [ ] **Step 4: Export from the package `__init__`**

In `backend/app/modules/ppe/__init__.py`, add to the imports and `__all__` (mirror the existing symbol list):

```python
from app.modules.ppe.stock import (
    Allocation,
    InsufficientStockError,
    StockBatchNotFound,
    allocate_fifo,
    deplete_for_issue,
    record_movement,
)
```
and add each name to `__all__`:
```python
    "Allocation",
    "InsufficientStockError",
    "StockBatchNotFound",
    "allocate_fifo",
    "deplete_for_issue",
    "record_movement",
```

> `deplete_for_issue` is imported here now but defined in Task 5 — add the import line now; the name resolves once Task 5 lands. If running Task 4 in isolation, temporarily omit `deplete_for_issue` from this import and add it in Task 5.

- [ ] **Step 5: Run to verify it passes**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_service.py -q`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/ppe/stock.py backend/app/modules/ppe/__init__.py tests/api/test_ppe_stock_movements_service.py
git commit -m "feat(p10-06): record_movement service (receipt/writeoff/adjustment)"
```

---

### Task 5: `deplete_for_issue` DB service (FIFO + flag + no-op guards)

**Files:**
- Modify: `backend/app/modules/ppe/stock.py`
- Test: `tests/api/test_ppe_stock_movements_service.py` (append)

- [ ] **Step 1: Write the failing tests (append to the service test file)**

Append to `tests/api/test_ppe_stock_movements_service.py`:

```python
from datetime import date

from app.models.feature import Feature, FeatureEnablement
from app.modules.ppe.stock import deplete_for_issue


async def _enable_warehouse(session, tenant_id: str) -> None:
    feature = Feature(code="warehouse", title="Warehouse")
    session.add(feature)
    await session.flush()
    session.add(FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=True))
    await session.flush()


@pytest.mark.asyncio
async def test_deplete_fifo_spans_batches_oldest_first(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Перчатки")
        session.add(item)
        await session.flush()
        old = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="OLD", quantity=3,
            received_at=date(2026, 1, 1),
        )
        new = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="NEW", quantity=10,
            received_at=date(2026, 6, 1),
        )
        session.add_all([old, new])
        await session.flush()

        movements = await deplete_for_issue(
            session, tenant_id=tenant.id, item_id=item.id, quantity=7, ref_id="issue-1"
        )
        await session.refresh(old)
        await session.refresh(new)

    assert old.quantity == 0  # oldest drained first
    assert new.quantity == 6  # remainder from newer
    assert [m.quantity_delta for m in movements] == [-3, -4]
    assert all(m.kind == "issue" and m.ref_type == "ppe_issue" and m.ref_id == "issue-1" for m in movements)


@pytest.mark.asyncio
async def test_deplete_explicit_batch_only(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        b1 = PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B-1", quantity=5, received_at=date(2026, 1, 1))
        b2 = PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B-2", quantity=5, received_at=date(2026, 2, 1))
        session.add_all([b1, b2])
        await session.flush()

        movements = await deplete_for_issue(
            session, tenant_id=tenant.id, item_id=item.id, quantity=2, batch_id=b2.id, ref_id="issue-2"
        )
        await session.refresh(b1)
        await session.refresh(b2)

    assert b1.quantity == 5  # untouched: explicit override picked b2
    assert b2.quantity == 3
    assert len(movements) == 1 and movements[0].batch_id == b2.id


@pytest.mark.asyncio
async def test_deplete_insufficient_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        session.add(PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B", quantity=2))
        await session.flush()
        with pytest.raises(InsufficientStockError):
            await deplete_for_issue(
                session, tenant_id=tenant.id, item_id=item.id, quantity=5, ref_id="i"
            )


@pytest.mark.asyncio
async def test_deplete_noop_when_item_has_no_batches(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        movements = await deplete_for_issue(
            session, tenant_id=tenant.id, item_id=item.id, quantity=3, ref_id="i"
        )
    assert movements == []


@pytest.mark.asyncio
async def test_deplete_noop_when_flag_disabled(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # explicit opt-out
        feature = Feature(code="warehouse", title="Warehouse")
        session.add(feature)
        await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=False))
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        session.add(PPEStockBatch(tenant_id=tenant.id, item_id=item.id, batch_no="B", quantity=10))
        await session.flush()
        movements = await deplete_for_issue(
            session, tenant_id=tenant.id, item_id=item.id, quantity=3, ref_id="i"
        )
        batch = (
            await session.execute(
                select(PPEStockBatch).where(PPEStockBatch.item_id == item.id)
            )
        ).scalar_one()
    assert movements == []
    assert batch.quantity == 10  # untouched when flag off
```

Add the `select` import at the top of the test file if not present:
```python
from sqlalchemy import select
```

- [ ] **Step 2: Run to verify it fails**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_service.py -k deplete -q`
Expected: FAIL — `ImportError: cannot import name 'deplete_for_issue'`.

- [ ] **Step 3: Add `deplete_for_issue` to `stock.py`**

Append to `backend/app/modules/ppe/stock.py`:

```python
async def deplete_for_issue(
    session: AsyncSession,
    *,
    tenant_id: str,
    item_id: str,
    quantity: int,
    batch_id: str | None = None,
    ref_id: str,
) -> list[PPEStockMovement]:
    """Deplete stock for a worker issuance. Returns the ``issue`` movements.

    No-op (returns ``[]``) when the warehouse flag is off for the tenant or the
    item has no stock batches — this preserves the pre-ledger issuance behaviour.
    Explicit ``batch_id`` depletes that batch; otherwise FIFO by ``received_at``
    (nulls last), ``id`` tiebreaker. Raises :class:`InsufficientStockError` when
    the requested quantity exceeds available on-hand.
    """
    if quantity <= 0:
        return []
    if not await is_feature_enabled(session, tenant_id, WAREHOUSE_FEATURE_CODE):
        return []

    if batch_id is not None:
        candidates = [await _load_batch(session, tenant_id, batch_id, item_id=item_id)]
    else:
        stmt = (
            select(PPEStockBatch)
            .where(
                PPEStockBatch.tenant_id == tenant_id,
                PPEStockBatch.item_id == item_id,
                PPEStockBatch.deleted_at.is_(None),
                PPEStockBatch.quantity > 0,
            )
            # portable NULLS LAST: is_(None) sorts False(0) before True(1)
            .order_by(
                PPEStockBatch.received_at.is_(None),
                PPEStockBatch.received_at.asc(),
                PPEStockBatch.id.asc(),
            )
        )
        candidates = list((await session.execute(stmt)).scalars().all())
        if not candidates:
            return []

    by_id = {b.id: b for b in candidates}
    allocations = allocate_fifo([(b.id, b.quantity) for b in candidates], quantity)

    movements: list[PPEStockMovement] = []
    for alloc in allocations:
        movements.append(
            await _write_movement(
                session,
                tenant_id=tenant_id,
                batch=by_id[alloc.batch_id],
                kind=KIND_ISSUE,
                delta=-alloc.taken,
                ref_type="ppe_issue",
                ref_id=ref_id,
            )
        )
    return movements
```

- [ ] **Step 4: Run to verify it passes**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_service.py -q`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/stock.py tests/api/test_ppe_stock_movements_service.py
git commit -m "feat(p10-06): deplete_for_issue FIFO service with flag/no-batch no-op"
```

---

### Task 6: Schemas — movement DTOs, issue `batch_id`, drop batch-update `quantity`

**Files:**
- Modify: `backend/app/schemas/ppe.py`
- Test: `tests/unit/test_ppe_stock_movement_schema.py`

- [ ] **Step 1: Write the failing schema tests**

Create `tests/unit/test_ppe_stock_movement_schema.py`:

```python
"""Schema contract for stock movements + issue batch_id (P10-06)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ppe import (
    PPEIssueCreate,
    PPEStockBatchUpdate,
    PPEStockMovementCreate,
)


def test_movement_create_accepts_valid_kind() -> None:
    m = PPEStockMovementCreate(batch_id="b1", kind="receipt", quantity=5)
    assert m.kind == "receipt"


def test_movement_create_rejects_issue_kind() -> None:
    with pytest.raises(ValidationError):
        PPEStockMovementCreate(batch_id="b1", kind="issue", quantity=5)


def test_movement_create_rejects_unknown_kind() -> None:
    with pytest.raises(ValidationError):
        PPEStockMovementCreate(batch_id="b1", kind="teleport", quantity=5)


def test_issue_create_has_optional_batch_id() -> None:
    assert PPEIssueCreate(person_id="p", item_id="i").batch_id is None
    assert PPEIssueCreate(person_id="p", item_id="i", batch_id="b").batch_id == "b"


def test_batch_update_drops_quantity() -> None:
    assert "quantity" not in PPEStockBatchUpdate.model_fields
```

- [ ] **Step 2: Run to verify it fails**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/unit/test_ppe_stock_movement_schema.py -q`
Expected: FAIL — `ImportError: cannot import name 'PPEStockMovementCreate'`.

- [ ] **Step 3: Edit `backend/app/schemas/ppe.py`**

(a) Add `batch_id` to `PPEIssueCreate` (after `signature_doc_ref`, ~line 103):

```python
class PPEIssueCreate(BaseSchema):
    person_id: str
    item_id: str
    quantity: int = Field(default=1, ge=1)
    issued_at: datetime | None = None
    wear_days: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    certificate_no: str | None = Field(default=None, max_length=255)
    wear_percent: int | None = Field(default=None, ge=0, le=100)
    signature_doc_ref: str | None = Field(default=None, max_length=255)
    batch_id: str | None = None  # P10-06: explicit stock batch to deplete (else FIFO)
```

(b) Add `batch_id` to `PPEIssueReplaceRequest` (find the class; it currently has `item_id`/`quantity`/`wear_days`/... — add one line):

```python
    batch_id: str | None = None  # P10-06: explicit stock batch to deplete (else FIFO)
```

(c) Remove `quantity` from `PPEStockBatchUpdate` (delete line 215):

```python
class PPEStockBatchUpdate(BaseSchema):
    batch_no: str | None = None
    received_at: date | None = None
    certificate_no: str | None = None
    certificate_expires_at: date | None = None
    location: str | None = None
```

(d) Add movement schemas at the end of the file (after `PPEStockLevelPage`, line 250):

```python
_MOVEMENT_MANUAL_KINDS = {"receipt", "writeoff", "adjustment"}


class PPEStockMovementCreate(BaseSchema):
    batch_id: str
    kind: str
    quantity: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None

    @field_validator("kind")
    @classmethod
    def _validate_kind(cls, value: str) -> str:
        if value not in _MOVEMENT_MANUAL_KINDS:
            raise ValueError(
                "kind must be one of receipt/writeoff/adjustment "
                "(issue movements are created by the issuance flow)"
            )
        return value


class PPEStockMovementRead(BaseSchema):
    id: str
    item_id: str
    batch_id: str | None
    kind: str
    quantity_delta: int
    occurred_at: datetime
    reason: str | None
    ref_type: str | None
    ref_id: str | None
    created_at: datetime


class PPEStockMovementPage(BaseSchema):
    items: list[PPEStockMovementRead]
    total: int
```

(`field_validator` and `Field` are already imported at the top of this file, line 8.)

- [ ] **Step 4: Run to verify it passes**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/unit/test_ppe_stock_movement_schema.py -q`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/ppe.py tests/unit/test_ppe_stock_movement_schema.py
git commit -m "feat(p10-06): stock movement schemas + issue batch_id; drop batch-update quantity"
```

---

### Task 7: Routes — movements endpoints + opening-receipt on batch create + fix batch PATCH test

**Files:**
- Modify: `backend/app/api/routes/ppe.py`
- Modify: `tests/api/test_ppe_warehouse_api.py` (fix `test_create_list_get_patch_batch`)
- Test: `tests/api/test_ppe_stock_movements_api.py`

- [ ] **Step 1: Write the failing movements-API tests**

Create `tests/api/test_ppe_stock_movements_api.py`:

```python
"""API contract for PPE stock movements (P10-06)."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _seed_item(async_client: AsyncClient, headers: dict, *, name: str = "Каска") -> str:
    resp = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


async def _seed_batch(async_client, headers, item_id, *, no="B-1", qty=10) -> str:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": no, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_receipt_movement_updates_levels(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10)

    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "receipt", "quantity": 5, "reason": "поступление"},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    assert resp.json()["quantity_delta"] == 5

    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    row = next(r for r in levels.json()["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 15


@pytest.mark.asyncio
async def test_writeoff_insufficient_returns_400(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=2)

    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "writeoff", "quantity": 5},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_issue_kind_rejected_on_manual_endpoint(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=5)
    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "issue", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_list_movements_filters_and_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10)
    await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_id, "kind": "writeoff", "quantity": 1},
        headers=headers,
    )

    listed = await async_client.get(
        f"/api/v1/ppe/stock/movements?batch_id={batch_id}", headers=headers
    )
    assert listed.status_code == status.HTTP_200_OK
    kinds = {m["kind"] for m in listed.json()["items"]}
    assert "writeoff" in kinds  # includes the opening receipt + writeoff
    etag = listed.headers.get("etag")
    assert etag
    again = await async_client.get(
        f"/api/v1/ppe/stock/movements?batch_id={batch_id}",
        headers={**headers, "if-none-match": etag},
    )
    assert again.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_movements_tenant_isolation(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()
    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    item_a = await _seed_item(async_client, headers_a)
    batch_a = await _seed_batch(async_client, headers_a, item_a, qty=5)

    headers_b = await make_auth_headers(
        RoleEnum.ADMIN, tenant="beta", email="admin-beta@example.com"
    )
    resp = await async_client.post(
        "/api/v1/ppe/stock/movements",
        json={"batch_id": batch_a, "kind": "receipt", "quantity": 1},
        headers=headers_b,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND  # batch invisible cross-tenant
```

- [ ] **Step 2: Run to verify it fails**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_api.py -q`
Expected: FAIL — 404/405 on `/ppe/stock/movements` (route missing).

- [ ] **Step 3: Wire imports in `backend/app/api/routes/ppe.py`**

Add to the `from app.modules.ppe import (...)` block (line 27-34):

```python
from app.modules.ppe import (
    build_personal_card_766n,
    deplete_for_issue,
    issue_ppe_item,
    list_expiring_issues,
    record_movement,
    replace_issue,
    return_issue,
    writeoff_issue,
)
from app.modules.ppe.stock import InsufficientStockError, StockBatchNotFound
```

Add to the `from app.schemas.ppe import (...)` block (line 36-63):

```python
    PPEStockMovementCreate,
    PPEStockMovementPage,
    PPEStockMovementRead,
```

Also import the model for the list query — add to the `from app.models.ppe_registry import ...` line (line 24):

```python
from app.models.ppe_registry import (
    PPEIssue,
    PPEIssueStatus,
    PPEItem,
    PPEStockBatch,
    PPEStockMovement,
)
```

- [ ] **Step 4: Add the movements endpoints**

In `backend/app/api/routes/ppe.py`, immediately after `list_stock_levels` (ends line 956), add:

```python
@router.post(
    "/stock/movements",
    response_model=PPEStockMovementRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("create", "ppe_stock_movement")
async def create_stock_movement(
    payload: PPEStockMovementCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEStockMovementRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        movement = await record_movement(
            session,
            tenant_id=tenant.id,
            batch_id=payload.batch_id,
            kind=payload.kind,
            quantity=payload.quantity,
            reason=payload.reason,
            occurred_at=payload.occurred_at,
        )
    except StockBatchNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InsufficientStockError as exc:
        raise _ppe_bad_request(str(exc)) from exc
    except ValueError as exc:
        raise _ppe_bad_request(str(exc)) from exc
    return PPEStockMovementRead.model_validate(movement)


@router.get(
    "/stock/movements",
    response_model=PPEStockMovementPage,
    dependencies=[WarehouseFeatureGate],
)
async def list_stock_movements(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    item_id: str | None = None,
    batch_id: str | None = None,
    kind: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEStockMovementPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    base = select(PPEStockMovement).where(PPEStockMovement.tenant_id == tenant.id)
    if item_id:
        base = base.where(PPEStockMovement.item_id == item_id)
    if batch_id:
        base = base.where(PPEStockMovement.batch_id == batch_id)
    if kind:
        base = base.where(PPEStockMovement.kind == kind)

    stmt = base.order_by(
        PPEStockMovement.occurred_at.desc(), PPEStockMovement.id.desc()
    ).limit(limit).offset(offset)
    movements = list((await session.execute(stmt)).scalars().all())

    count_stmt = select(func.count()).select_from(base.subquery())
    total = (await session.execute(count_stmt)).scalar_one()

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=movements,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("item", item_id or ""),
            ("batch", batch_id or ""),
            ("kind", kind or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PPEStockMovementPage(
        items=[PPEStockMovementRead.model_validate(m) for m in movements], total=total
    )
```

- [ ] **Step 5: Change `create_stock_batch` to write an opening receipt**

Replace the body of `create_stock_batch` (lines 847-870) so the batch starts at 0 and the initial quantity is booked as a `receipt` movement (keeps the journal complete and the invariant intact):

```python
async def create_stock_batch(
    payload: PPEStockBatchCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEStockBatchRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_item(session, tenant, payload.item_id)

    batch = PPEStockBatch(
        tenant_id=tenant.id,
        item_id=payload.item_id,
        batch_no=payload.batch_no,
        quantity=0,
        received_at=payload.received_at,
        certificate_no=payload.certificate_no,
        certificate_expires_at=payload.certificate_expires_at,
        location=payload.location,
    )
    session.add(batch)
    await session.flush()
    if payload.quantity > 0:
        await record_movement(
            session,
            tenant_id=tenant.id,
            batch_id=batch.id,
            kind="receipt",
            quantity=payload.quantity,
            reason="opening balance",
        )
    await session.refresh(batch)
    return PPEStockBatchRead.model_validate(batch)
```

- [ ] **Step 6: Fix the existing batch-PATCH test (quantity is no longer patchable)**

In `tests/api/test_ppe_warehouse_api.py`, in `test_create_list_get_patch_batch`, replace the PATCH block (lines 85-89) with a metadata-field patch:

```python
    patched = await async_client.patch(
        f"/api/v1/ppe/stock/batches/{batch_id}",
        json={"location": "Склад-2"},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["location"] == "Склад-2"
    assert patched.json()["quantity"] == 25  # quantity unchanged: not patchable
```

- [ ] **Step 7: Run the movements-API tests + the warehouse regression to verify pass**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_warehouse_api.py -q`
Expected: all passed (movements 5 + warehouse 7).

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/routes/ppe.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_warehouse_api.py
git commit -m "feat(p10-06): stock movements endpoints + opening-receipt on batch create"
```

---

### Task 8: Wire depletion into issuance (create + replace)

**Files:**
- Modify: `backend/app/api/routes/ppe.py` (`create_issue` ~514-557, `replace_issue_endpoint` ~648-693)
- Test: `tests/api/test_ppe_stock_movements_api.py` (append)

- [ ] **Step 1: Write the failing issuance-depletion tests (append)**

Append to `tests/api/test_ppe_stock_movements_api.py`:

```python
async def _seed_person(async_client, headers, *, name="Иванов") -> str:
    resp = await async_client.post(
        "/api/v1/persons",
        json={"last_name": name, "first_name": "Иван"},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_issue_depletes_stock_fifo(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id, no="B-1", qty=10)
    person_id = await _seed_person(async_client, headers)

    issued = await async_client.post(
        "/api/v1/ppe/issues",
        json={"person_id": person_id, "item_id": item_id, "quantity": 3},
        headers=headers,
    )
    assert issued.status_code == status.HTTP_201_CREATED, issued.text

    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    row = next(r for r in levels.json()["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 7  # 10 - 3


@pytest.mark.asyncio
async def test_issue_insufficient_stock_400_and_no_issue(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id, no="B-1", qty=2)
    person_id = await _seed_person(async_client, headers)

    resp = await async_client.post(
        "/api/v1/ppe/issues",
        json={"person_id": person_id, "item_id": item_id, "quantity": 5},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST

    # rollback: no issue persisted, stock unchanged
    issues = await async_client.get(f"/api/v1/ppe/issues?person_id={person_id}", headers=headers)
    assert issues.json()["total"] == 0
    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    row = next(r for r in levels.json()["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 2


@pytest.mark.asyncio
async def test_issue_without_batches_is_noop(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)  # no batches
    person_id = await _seed_person(async_client, headers)

    issued = await async_client.post(
        "/api/v1/ppe/issues",
        json={"person_id": person_id, "item_id": item_id, "quantity": 3},
        headers=headers,
    )
    assert issued.status_code == status.HTTP_201_CREATED  # backward compatible


@pytest.mark.asyncio
async def test_issue_explicit_batch_id(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    b1 = await _seed_batch(async_client, headers, item_id, no="B-1", qty=5)
    b2 = await _seed_batch(async_client, headers, item_id, no="B-2", qty=5)
    person_id = await _seed_person(async_client, headers)

    issued = await async_client.post(
        "/api/v1/ppe/issues",
        json={"person_id": person_id, "item_id": item_id, "quantity": 2, "batch_id": b2},
        headers=headers,
    )
    assert issued.status_code == status.HTTP_201_CREATED, issued.text

    b1_movements = await async_client.get(
        f"/api/v1/ppe/stock/movements?batch_id={b1}", headers=headers
    )
    # b1 has only its opening receipt (no issue movement)
    assert all(m["kind"] != "issue" for m in b1_movements.json()["items"])
    b2_movements = await async_client.get(
        f"/api/v1/ppe/stock/movements?batch_id={b2}", headers=headers
    )
    assert any(m["kind"] == "issue" and m["quantity_delta"] == -2 for m in b2_movements.json()["items"])
```

> If the persons endpoint path differs (`/api/v1/persons` body shape), align `_seed_person` with the nearest existing person-creation test (`grep -rn "ppe/issues" tests/api/test_ppe_issue_operations_api.py` shows the person fixture used there — reuse that helper's shape).

- [ ] **Step 2: Run to verify it fails**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_api.py -k issue -q`
Expected: FAIL — `test_issue_depletes_stock_fifo` sees `total_quantity == 10` (no depletion) / insufficient test returns 201.

- [ ] **Step 3: Wire `deplete_for_issue` into `create_issue`**

In `create_issue`, after the `issue = await issue_ppe_item(...)` try/except (line 539) and BEFORE `outbox = OutboxService(session)` (line 540), insert:

```python
    try:
        await deplete_for_issue(
            session,
            tenant_id=str(tenant.id),
            item_id=issue.item_id,
            quantity=issue.quantity,
            batch_id=payload.batch_id,
            ref_id=issue.id,
        )
    except StockBatchNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InsufficientStockError as exc:
        raise _ppe_bad_request(str(exc)) from exc
```

- [ ] **Step 4: Wire `deplete_for_issue` into `replace_issue_endpoint`**

In `replace_issue_endpoint`, after `_old, new_issue = result` (line 675) and BEFORE `outbox = OutboxService(session)` (line 676), insert:

```python
    try:
        await deplete_for_issue(
            session,
            tenant_id=str(tenant.id),
            item_id=new_issue.item_id,
            quantity=new_issue.quantity,
            batch_id=payload.batch_id,
            ref_id=new_issue.id,
        )
    except StockBatchNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except InsufficientStockError as exc:
        raise _ppe_bad_request(str(exc)) from exc
```

- [ ] **Step 5: Run the depletion tests + issue-operations regression**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_issue_operations_api.py tests/api/test_ppe_api.py tests/api/test_ppe_events.py -q`
Expected: all passed (new depletion tests green; existing issuance tests unaffected — their items have no batches → no-op).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/ppe.py tests/api/test_ppe_stock_movements_api.py
git commit -m "feat(p10-06): deplete stock (FIFO) on PPE issue + replace"
```

---

### Task 9: Frontend — Movements section + manual receipt/adjustment form

**Files:**
- Modify: `frontend/src/api/warehouse.ts`
- Modify: `frontend/src/pages/warehouse/WarehousePage.tsx`
- Modify: `frontend/src/__tests__/WarehousePage.test.tsx`

- [ ] **Step 1: Write the failing frontend test**

Replace `frontend/src/__tests__/WarehousePage.test.tsx` with (adds `listMovements`/`createMovement` to the mock and asserts a movement renders):

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import WarehousePage from "@/pages/warehouse/WarehousePage";

const listLevelsMock = vi.fn();
const listBatchesMock = vi.fn();
const listMovementsMock = vi.fn();
const createMovementMock = vi.fn();

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...args: unknown[]) => listLevelsMock(...args),
    listBatches: (...args: unknown[]) => listBatchesMock(...args),
    listMovements: (...args: unknown[]) => listMovementsMock(...args),
    createMovement: (...args: unknown[]) => createMovementMock(...args)
  }
}));

describe("WarehousePage", () => {
  beforeEach(() => {
    listLevelsMock.mockReset();
    listBatchesMock.mockReset();
    listMovementsMock.mockReset();
    createMovementMock.mockReset();
    listMovementsMock.mockResolvedValue([]);
  });

  it("renders stock levels from the warehouse API", async () => {
    listLevelsMock.mockResolvedValue([
      { item_id: "i1", item_name: "Каска", total_quantity: 12, batch_count: 2, nearest_certificate_expiry: null }
    ]);
    listBatchesMock.mockResolvedValue([
      { id: "b1", item_id: "i1", batch_no: "B-1", quantity: 12, created_at: "2026-05-29T00:00:00Z", updated_at: "2026-05-29T00:00:00Z" }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Каска")).toBeInTheDocument());
    expect(screen.getByText("Партий: 1")).toBeInTheDocument();
  });

  it("renders recent movements", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    listMovementsMock.mockResolvedValue([
      { id: "m1", item_id: "i1", batch_id: "b1", kind: "receipt", quantity_delta: 5, occurred_at: "2026-07-02T00:00:00Z", reason: "поступление", ref_type: null, ref_id: null, created_at: "2026-07-02T00:00:00Z" }
    ]);

    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Движения")).toBeInTheDocument());
    expect(screen.getByText("поступление")).toBeInTheDocument();
  });

  it("shows an empty state when there are no levels", async () => {
    listLevelsMock.mockResolvedValue([]);
    listBatchesMock.mockResolvedValue([]);
    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("Позиции не найдены")).toBeInTheDocument());
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm --prefix frontend run test -- WarehousePage`
Expected: FAIL — `listMovements is not a function` / "Движения" not found.

- [ ] **Step 3: Extend `frontend/src/api/warehouse.ts`**

Append the movement type + methods (keep existing exports):

```ts
export type StockMovementDto = {
  id: string;
  item_id: string;
  batch_id: string | null;
  kind: "receipt" | "issue" | "writeoff" | "adjustment";
  quantity_delta: number;
  occurred_at: string;
  reason?: string | null;
  ref_type?: string | null;
  ref_id?: string | null;
  created_at: string;
};

export type CreateMovementInput = {
  batch_id: string;
  kind: "receipt" | "writeoff" | "adjustment";
  quantity: number;
  reason?: string | null;
};
```

Add two methods inside the `warehouseApi` object (after `listLevels`):

```ts
  async listMovements(): Promise<StockMovementDto[]> {
    const response = await apiClient.get<PageResponse<StockMovementDto>>("/ppe/stock/movements", {
      params: { limit: 50, offset: 0 }
    });
    return response.data.items ?? [];
  },
  async createMovement(input: CreateMovementInput): Promise<StockMovementDto> {
    const response = await apiClient.post<StockMovementDto>("/ppe/stock/movements", input);
    return response.data;
  }
```

- [ ] **Step 4: Add the Movements section to `WarehousePage.tsx`**

(a) Extend imports and state. Add to the top imports:

```tsx
import { Button } from "@/components/ui/button";
import { warehouseApi, type StockBatchDto, type StockLevelDto, type StockMovementDto } from "@/api/warehouse";
```

(remove the old `warehouseApi` import line to avoid a duplicate.)

(b) Add state + form state after `const [batches, setBatches] = useState<StockBatchDto[]>([]);`:

```tsx
  const [movements, setMovements] = useState<StockMovementDto[]>([]);
  const [form, setForm] = useState({ batch_id: "", kind: "receipt", quantity: "1", reason: "" });
  const [submitting, setSubmitting] = useState(false);
```

(c) In `load()`, add movements to the parallel fetch:

```tsx
      const [levelsData, batchesData, movementsData] = await Promise.all([
        warehouseApi.listLevels(),
        warehouseApi.listBatches(),
        warehouseApi.listMovements()
      ]);
      setLevels(levelsData);
      setBatches(batchesData);
      setMovements(movementsData);
```

(d) Add a submit handler after `load`:

```tsx
  const submitMovement = async () => {
    if (!form.batch_id) return;
    setSubmitting(true);
    try {
      await warehouseApi.createMovement({
        batch_id: form.batch_id,
        kind: form.kind as "receipt" | "writeoff" | "adjustment",
        quantity: Number(form.quantity) || 0,
        reason: form.reason || null
      });
      setForm({ batch_id: "", kind: "receipt", quantity: "1", reason: "" });
      await load();
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось провести движение" });
    } finally {
      setSubmitting(false);
    }
  };
```

(e) Add a "Движения" card just before the closing `</div>` of the outer container (after the "Остатки по номенклатуре" card, before line 143 `</div>`):

```tsx
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Движения</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid gap-2 md:grid-cols-5">
            <Input
              placeholder="ID партии"
              value={form.batch_id}
              onChange={(e) => setForm({ ...form, batch_id: e.target.value })}
            />
            <select
              className="h-9 rounded-md border border-input bg-background px-2 text-sm"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
            >
              <option value="receipt">Приход</option>
              <option value="writeoff">Списание</option>
              <option value="adjustment">Корректировка (до факт.)</option>
            </select>
            <Input
              type="number"
              min={0}
              value={form.quantity}
              onChange={(e) => setForm({ ...form, quantity: e.target.value })}
            />
            <Input
              placeholder="Причина"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
            />
            <Button onClick={submitMovement} disabled={submitting || !form.batch_id}>
              Провести
            </Button>
          </div>
          {movements.length === 0 ? (
            <EmptyState title="Движений нет" description="Проведите приход или корректировку по партии." />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Дата</TableHead>
                  <TableHead>Тип</TableHead>
                  <TableHead>Δ Кол-во</TableHead>
                  <TableHead>Причина</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {movements.map((m) => (
                  <TableRow key={m.id}>
                    <TableCell>{formatDate(m.occurred_at) || "—"}</TableCell>
                    <TableCell>{m.kind}</TableCell>
                    <TableCell>{m.quantity_delta}</TableCell>
                    <TableCell>{m.reason || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
```

> If `@/components/ui/button` does not exist at that path, `grep -rn "components/ui/button" frontend/src` to find the correct Button import (repo uses shadcn/ui — a Button primitive exists; adjust the import path only).

- [ ] **Step 5: Run the frontend test to verify it passes**

Run: `npm --prefix frontend run test -- WarehousePage`
Expected: 3 passed.

- [ ] **Step 6: Typecheck + build**

Run: `npm --prefix frontend run typecheck && npm --prefix frontend run build`
Expected: exit 0 for both.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/warehouse.ts frontend/src/pages/warehouse/WarehousePage.tsx frontend/src/__tests__/WarehousePage.test.tsx
git commit -m "feat(p10-06): warehouse movements UI (list + manual receipt/adjustment)"
```

---

### Task 10: Gates, OpenAPI resnap, docs

**Files:**
- Modify: OpenAPI baseline (path reported by the guard)
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`
- Modify: `AI_IMPLEMENTATION_REPORT.md`
- Modify: `CHANGELOG.md` (if present at repo root)

- [ ] **Step 1: Backend lint**

Run: `& "D:\...\.venv\Scripts\python.exe" -m ruff check backend/app/modules/ppe/stock.py backend/app/api/routes/ppe.py backend/app/models/ppe.py backend/app/schemas/ppe.py && & "D:\...\.venv\Scripts\python.exe" -m black --check backend/app/modules/ppe/stock.py backend/app/api/routes/ppe.py`
Expected: clean (run `black` without `--check` to auto-format if it complains, then re-commit).

- [ ] **Step 2: Re-snapshot the OpenAPI baseline (sanctioned additive contract change)**

The new `/ppe/stock/movements` routes + the `batch_id` issue field + the removed `quantity` batch-update field change the OpenAPI. Re-snap:

Run: `& "D:\...\.venv\Scripts\python.exe" scripts/ci/check_openapi_snapshot.py --snapshot`
Then verify the guard passes without `--snapshot`:
Run: `& "D:\...\.venv\Scripts\python.exe" scripts/ci/check_openapi_snapshot.py`
Expected: exit 0. Note the new endpoint/schema counts in the commit message (previous baseline was 808/648 after RC-014).

- [ ] **Step 3: Celery task guard (unchanged, confirm green)**

Run: `& "D:\...\.venv\Scripts\python.exe" scripts/ci/check_celery_tasks.py`
Expected: exit 0 (no new Celery tasks added).

- [ ] **Step 4: PG16 migration gate (validates `wa04` + enum parity + boundaries)**

Run (from PowerShell, Docker running): `python scripts/ci/local_gate.py --db-only`
Expected: green — `alembic upgrade heads` includes `wa04`, round-trip downgrade/upgrade passes, enum-parity + boundary guards pass.

> If Docker/PG16 is unavailable in this environment, record that `--db-only` was not run locally and must run on the reference workstation before merge (per the permanent local-evidence policy). Do not claim the migration is validated without it.

- [ ] **Step 5: Update the roadmap status line**

In `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, the `P10-06` row currently reads `🟡 skeleton only ... Остаётся ... перемещения, поставщики, бюджет безопасности, мобильная выдача, прогноз дефицита`. Update the evidence cell to note the movements ledger landed:

```
| **P10-06** | СИЗ склад (полный) | 🟡 **skeleton + движения** | `PPEStockBatch` + `PPEStockMovement` (append-only журнал, migration `wa04`); `/ppe/stock/movements` (receipt/writeoff/adjustment) + FIFO-списание при выдаче (`deplete_for_issue`); honest `/stock/levels`. **Остаётся:** перемещения, поставщики, бюджет безопасности, мин-остаток/прогноз дефицита, инвентаризация, мобильная выдача |
```

- [ ] **Step 6: Add a handoff journal entry**

Prepend a `## Last Agent Handoff (2026-07-02, P10-06 СИЗ СКЛАД — ЖУРНАЛ ДВИЖЕНИЙ ...)` block at the top of `AI_IMPLEMENTATION_REPORT.md` (after the title, before the current top handoff), summarizing: model `PPEStockMovement` + migration `wa04`; service `modules/ppe/stock.py` (allocate_fifo/record_movement/deplete_for_issue); route-level depletion wiring; opening-receipt on batch create; `quantity` removed from batch PATCH; OpenAPI resnap; tests green; PG gate status; next slice candidates (reorder alerts, inventory count). Branch `feat/ppe-stock-movements-p10-06`, base `main`.

- [ ] **Step 7: CHANGELOG (if present)**

If `CHANGELOG.md` exists at repo root, add under the unreleased/top section:

```
- P10-06 СИЗ склад: append-only stock movements ledger (`ppe_stock_movement`, migration wa04); FIFO stock depletion on PPE issue; manual receipt/writeoff/adjustment endpoints; honest `/ppe/stock/levels`. Batch `quantity` no longer PATCHable (use movements).
```

- [ ] **Step 8: Full PPE + warehouse regression sweep**

Run: `& "D:\...\.venv\Scripts\python.exe" -m pytest backend/tests/test_wa04_ppe_stock_movement_migration.py tests/unit/test_ppe_stock_allocation.py tests/unit/test_ppe_stock_movement_schema.py tests/api/test_ppe_stock_movements_service.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_warehouse_api.py tests/api/test_ppe_warehouse_cache_etag_contract.py tests/api/test_ppe_api.py tests/api/test_ppe_issue_operations_api.py tests/api/test_ppe_events.py -q`
Expected: all passed. Judge by EXIT code (PowerShell buffering may drop the summary line).

- [ ] **Step 9: Commit**

```bash
git add docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md AI_IMPLEMENTATION_REPORT.md docs/stabilization/*openapi* CHANGELOG.md
git commit -m "docs(p10-06): roadmap status + handoff + OpenAPI resnap for stock movements"
```

---

## Self-Review

**1. Spec coverage:**
- Model `ppe_stock_movement` (kind/quantity_delta/ref strings, append-only, migration wa04) → Task 1, 2. ✅
- Cached-balance invariant + `record_movement` + opening receipt on batch create → Task 4, 7. ✅
- FIFO auto + explicit batch override + flag/no-batch no-op + 400 insufficient → Task 5 (service), Task 8 (route). ✅
- Endpoints `POST/GET /stock/movements`, `issue` rejected on manual endpoint, ETag, tenant-iso → Task 6, 7. ✅
- Retire raw PATCH `quantity` (+ fix existing test) → Task 6, 7. ✅
- Route-level depletion placement (create + replace) → Task 8. ✅
- Frontend movements section + form → Task 9. ✅
- Migration validated by PG gate; OpenAPI resnap; roadmap/handoff docs → Task 10. ✅
- Error-handling table (400 insufficient, 400 issue-kind→actually 422 at schema, 404 unknown/cross-tenant, flag-off) → covered by tests in Task 5/7/8. (Note: `kind=issue` is rejected at the **schema** layer → 422, stricter than the spec's 400; documented in Task 7 test `test_issue_kind_rejected_on_manual_endpoint`.) ✅

**2. Placeholder scan:** No TBD/TODO. Two "if the path/shape differs, grep …" notes (Button import, person-seed helper) are explicit fallbacks with the exact grep to run, not placeholders — the primary code is complete.

**3. Type consistency:** `allocate_fifo(available, quantity) -> list[Allocation]`, `Allocation(batch_id, taken)`, `record_movement(session, *, tenant_id, batch_id, kind, quantity, reason, occurred_at)`, `deplete_for_issue(session, *, tenant_id, item_id, quantity, batch_id, ref_id)`, `_write_movement(..., kind, delta, ...)` — names/signatures identical across Tasks 3/4/5/7/8. Schema names `PPEStockMovementCreate/Read/Page` consistent across Tasks 6/7. Frontend `listMovements`/`createMovement`/`StockMovementDto` consistent across Task 9. ✅

**4. Ordering assumption verified:** depletion runs after issue creation and before outbox enqueue, inside the same request transaction — an `InsufficientStockError` → 400 rolls back the whole request (issue not persisted, stock unchanged), asserted by `test_issue_insufficient_stock_400_and_no_issue`.
