# P10-06 PPE Stock Transfers Between Locations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add partial stock transfers between warehouse locations for PPE, expressed as a paired `transfer` ledger movements (`−q` source / `+q` destination) with a find-or-create destination batch, keeping per-item on-hand invariant and per-location balances honest.

**Architecture:** Reuse the existing append-only ledger (`PPEStockMovement`) and the single sanctioned balance mutator `_write_movement`. A transfer is one atomic service call `transfer_stock` that writes two `kind="transfer"` movements sharing a generated `ref_id`. The destination batch is find-or-created by `(item, batch_no, location)`; the batch unique key is extended with `location` (`NULLS NOT DISTINCT` on PG16, migration `wa07`). Three additive routes behind the `warehouse` feature flag: `POST /stock/transfers`, `GET /stock/transfers`, `GET /stock/levels/by-location`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 (async) / Alembic / Pydantic v2; React 18 / TypeScript / Vitest. Tests via pytest (`sessionmaker`, `data_factory`, `async_client`, `make_auth_headers` fixtures).

**Spec:** `docs/superpowers/specs/2026-07-04-p10-06-ppe-stock-transfers-design.md`

---

## File Structure

- **Modify** `backend/app/models/ppe.py` — replace `PPEStockBatch` unique constraint with a location-aware unique `Index`.
- **Create** `backend/app/migrations/versions/20260704_wa07_ppe_stock_batch_location_unique.py` — drop+add the unique key.
- **Modify** `backend/app/modules/ppe/stock.py` — add `KIND_TRANSFER`, `TransferResult`, `_find_or_create_dest_batch`, `transfer_stock`.
- **Modify** `backend/app/schemas/ppe.py` — add transfer + by-location DTOs.
- **Modify** `backend/app/api/routes/ppe.py` — add 3 routes.
- **Modify** `frontend/src/api/warehouse.ts` — add DTOs + 3 methods.
- **Modify** `frontend/src/pages/warehouse/WarehousePage.tsx` — add "Перемещения" section.
- **Create** `backend/tests/test_wa07_ppe_stock_batch_location_migration.py`
- **Create** `tests/api/test_ppe_stock_transfers_service.py`
- **Create** `tests/api/test_ppe_stock_transfers_api.py`
- **Create** `tests/unit/test_ppe_stock_transfer_schema.py`
- **Modify** `frontend/src/__tests__/WarehousePage.test.tsx`
- **Modify** docs: roadmap, CHANGELOG, OpenAPI baseline, handoff.

### Environment notes (this worktree)
- Run backend tests with the global interpreter (Git-Bash segfaults on pytest); PowerShell:
  `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest <path> -q`
  (canon is 3.12.12; note the local mismatch in output — do not abort).
- Frontend: `npm --prefix frontend run test -- <file>`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`.
- OpenAPI snapshot script needs `$env:PYTHONPATH="backend"`.
- `wa07` round-trip is validated only on the **PG16 gate** (SQLite does not carry the alembic chain): `python scripts/ci/local_gate.py --db-only` (or `make gate`).

---

## Task 1: Schema — batch unique key gains `location` (`wa07` + model)

**Files:**
- Modify: `backend/app/models/ppe.py` (`PPEStockBatch.__table_args__`, ~lines 156-159)
- Create: `backend/app/migrations/versions/20260704_wa07_ppe_stock_batch_location_unique.py`
- Test: `backend/tests/test_wa07_ppe_stock_batch_location_migration.py`

- [ ] **Step 1: Write the failing migration test**

Create `backend/tests/test_wa07_ppe_stock_batch_location_migration.py`:

```python
"""wa07 replaces the batch unique key with a location-aware unique index (P10-06)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "migrations"
    / "versions"
    / "20260704_wa07_ppe_stock_batch_location_unique.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa07_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIGRATION.exists(), "wa07 migration missing"


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260704_wa07_ppe_stock_batch_location_unique"
    assert mod.down_revision == "20260703_wa06_ppe_inventory_count"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_swaps_unique_key():
    src = _MIGRATION.read_text(encoding="utf-8")
    # drops the old (item, batch_no) unique constraint
    assert 'drop_constraint("uq_ppe_stock_batch_item_no"' in src
    # creates the new location-aware unique index with NULLS NOT DISTINCT
    assert "uq_ppe_stock_batch_item_no_loc" in src
    assert "nulls_not_distinct" in src.lower()
    # downgrade restores the old unique constraint
    assert 'create_unique_constraint("uq_ppe_stock_batch_item_no"' in src
    assert "add_column" not in src  # no existing-table column mutation
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest backend/tests/test_wa07_ppe_stock_batch_location_migration.py -q`
Expected: FAIL — migration file does not exist yet.

- [ ] **Step 3: Update the model unique key**

In `backend/app/models/ppe.py`, replace `PPEStockBatch.__table_args__`:

```python
    __table_args__ = (
        Index(
            "uq_ppe_stock_batch_item_no_loc",
            "tenant_id",
            "item_id",
            "batch_no",
            "location",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_ppe_stock_batch_item", "tenant_id", "item_id"),
    )
```

`Index` is already imported in this module (used by other tables). `UniqueConstraint` remains imported (used by `PPEItem`, `PPENorm`, etc.) — do not remove the import.

- [ ] **Step 4: Create the migration file**

Create `backend/app/migrations/versions/20260704_wa07_ppe_stock_batch_location_unique.py`:

```python
"""wa07: batch unique key includes location (partial transfers between locations).

Drops uq_ppe_stock_batch_item_no (tenant, item, batch_no) and replaces it with a
unique index over (tenant, item, batch_no, location) using NULLS NOT DISTINCT so a
batch_no can live in several locations while legacy NULL-location batches keep their
old dedup guarantee. Not purely additive (swaps a constraint) — PG16-gate verified.
"""

from __future__ import annotations

from alembic import op

revision = "20260704_wa07_ppe_stock_batch_location_unique"
down_revision = "20260703_wa06_ppe_inventory_count"
branch_labels = None
depends_on = None

_TABLE = "ppe_stock_batch"
_OLD = "uq_ppe_stock_batch_item_no"
_NEW = "uq_ppe_stock_batch_item_no_loc"


def upgrade() -> None:
    op.drop_constraint(_OLD, _TABLE, type_="unique")
    op.create_index(
        _NEW,
        _TABLE,
        ["tenant_id", "item_id", "batch_no", "location"],
        unique=True,
        postgresql_nulls_not_distinct=True,
    )


def downgrade() -> None:
    op.drop_index(_NEW, table_name=_TABLE)
    op.create_unique_constraint(
        _OLD, _TABLE, ["tenant_id", "item_id", "batch_no"]
    )
```

**Anti-грабли:** if the installed Alembic rejects `postgresql_nulls_not_distinct=` on `create_index`, fall back to raw DDL in `upgrade` (PG-only): `op.execute('CREATE UNIQUE INDEX uq_ppe_stock_batch_item_no_loc ON ppe_stock_batch (tenant_id, item_id, batch_no, location) NULLS NOT DISTINCT')` and keep the file-content test asserting `nulls_not_distinct` — adjust the assertion to `"NULLS NOT DISTINCT" in src` if you switch to raw DDL.

- [ ] **Step 5: Run the migration test to verify it passes**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest backend/tests/test_wa07_ppe_stock_batch_location_migration.py -q`
Expected: PASS (all 5 tests).

- [ ] **Step 6: Sanity-check the ORM still imports and single head**

Run: `$env:PYTHONPATH="backend"; C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -c "import app.models.ppe; import app.api.app; print('ok')"`
Expected: prints `ok` (no mapper/import error from the `Index` change).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/ppe.py backend/app/migrations/versions/20260704_wa07_ppe_stock_batch_location_unique.py backend/tests/test_wa07_ppe_stock_batch_location_migration.py
git commit -m "feat(p10-06): wa07 — batch unique key includes location (transfers)"
```

---

## Task 2: Service — `transfer_stock` happy path (partial split into a new destination batch)

**Files:**
- Modify: `backend/app/modules/ppe/stock.py`
- Test: `tests/api/test_ppe_stock_transfers_service.py`

- [ ] **Step 1: Write the failing service test**

Create `tests/api/test_ppe_stock_transfers_service.py`:

```python
"""DB-level tests for the PPE stock transfer service (P10-06)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.ppe_registry import PPEItem, PPEStockBatch, PPEStockMovement
from app.modules.ppe.stock import (
    InsufficientStockError,
    StockBatchNotFound,
    transfer_stock,
)
from tests.utils.factories import TestDataFactory


async def _item_and_batch(session, tenant_id, *, qty, location="A", no="B-1"):
    item = PPEItem(tenant_id=tenant_id, name="Каска")
    session.add(item)
    await session.flush()
    batch = PPEStockBatch(
        tenant_id=tenant_id, item_id=item.id, batch_no=no, quantity=qty, location=location
    )
    session.add(batch)
    await session.flush()
    return item, batch


async def _on_hand(session, tenant_id, item_id):
    rows = (
        await session.execute(
            select(PPEStockBatch.quantity).where(
                PPEStockBatch.tenant_id == tenant_id,
                PPEStockBatch.item_id == item_id,
                PPEStockBatch.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    return sum(int(q) for q in rows)


@pytest.mark.asyncio
async def test_partial_transfer_creates_dest_and_keeps_item_on_hand(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item, source = await _item_and_batch(session, tenant.id, qty=10, location="A")

        before = await _on_hand(session, tenant.id, item.id)
        result = await transfer_stock(
            session,
            tenant_id=tenant.id,
            source_batch_id=source.id,
            to_location="B",
            quantity=3,
        )
        await session.refresh(source)
        after = await _on_hand(session, tenant.id, item.id)

        dest = (
            await session.execute(
                select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id)
            )
        ).scalar_one()

    # source lost 3, a NEW dest batch at "B" gained 3, item on-hand unchanged
    assert source.quantity == 7
    assert dest.quantity == 3
    assert dest.location == "B"
    assert dest.batch_no == source.batch_no  # provenance preserved
    assert dest.id != source.id
    assert before == after == 10
    # two paired transfer movements sharing ref_id
    assert result.out_movement.kind == "transfer"
    assert result.in_movement.kind == "transfer"
    assert result.out_movement.quantity_delta == -3
    assert result.in_movement.quantity_delta == 3
    assert result.out_movement.ref_id == result.in_movement.ref_id == result.ref_id
    assert result.out_movement.ref_type == "ppe_transfer"
    assert result.from_location == "A"
    assert result.to_location == "B"
    assert result.batch_no == source.batch_no
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_service.py -q`
Expected: FAIL — `ImportError: cannot import name 'transfer_stock'`.

- [ ] **Step 3: Implement `transfer_stock` in `stock.py`**

In `backend/app/modules/ppe/stock.py`:

1. Add `from uuid import uuid4` to the imports block (top of file, after `from datetime import ...`).
2. Add the kind constant next to the other `KIND_*` constants:

```python
KIND_TRANSFER = "transfer"
```

3. Add the result dataclass (near `Allocation`) and the service functions (after `record_movement`, before `deplete_for_issue`):

```python
@dataclass(slots=True, frozen=True)
class TransferResult:
    ref_id: str
    out_movement: PPEStockMovement  # source, delta < 0
    in_movement: PPEStockMovement  # destination, delta > 0
    source_batch_id: str
    dest_batch_id: str
    batch_no: str
    from_location: str | None
    to_location: str
    quantity: int


async def _find_or_create_dest_batch(
    session: AsyncSession,
    *,
    tenant_id: str,
    source: PPEStockBatch,
    to_location: str,
) -> PPEStockBatch:
    """Find the sibling batch (same item + batch_no) at ``to_location`` or create it
    with quantity 0, copying the source batch provenance."""
    stmt = select(PPEStockBatch).where(
        PPEStockBatch.tenant_id == tenant_id,
        PPEStockBatch.item_id == source.item_id,
        PPEStockBatch.batch_no == source.batch_no,
        PPEStockBatch.location == to_location,
        PPEStockBatch.deleted_at.is_(None),
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        return existing
    dest = PPEStockBatch(
        tenant_id=tenant_id,
        item_id=source.item_id,
        batch_no=source.batch_no,
        quantity=0,
        location=to_location,
        received_at=source.received_at,
        certificate_no=source.certificate_no,
        certificate_expires_at=source.certificate_expires_at,
    )
    session.add(dest)
    await session.flush()
    return dest


async def transfer_stock(
    session: AsyncSession,
    *,
    tenant_id: str,
    source_batch_id: str,
    to_location: str,
    quantity: int,
    reason: str | None = None,
    occurred_at: datetime | None = None,
) -> TransferResult:
    """Move ``quantity`` of a batch from its location to ``to_location``.

    Emits a pair of ``transfer`` movements (source ``-quantity`` / destination
    ``+quantity``) sharing a generated ``ref_id`` via ``_write_movement`` — the only
    sanctioned balance mutator. Item-level on-hand is invariant (out + in = 0).
    The destination is a find-or-create sibling batch at ``to_location``.
    """
    if quantity <= 0:
        raise ValueError("transfer quantity must be positive")
    dest_location = (to_location or "").strip()
    if not dest_location:
        raise ValueError("transfer destination location must not be empty")
    source = await _load_batch(session, tenant_id, source_batch_id)
    if source.location == dest_location:
        raise ValueError("transfer destination must differ from source location")

    when = occurred_at or datetime.now(tz=timezone.utc)
    ref = uuid4().hex

    # Deplete the source first: an insufficient balance raises here, before any
    # destination batch is created (the whole call is one request transaction).
    out_movement = await _write_movement(
        session,
        tenant_id=tenant_id,
        batch=source,
        kind=KIND_TRANSFER,
        delta=-quantity,
        reason=reason,
        occurred_at=when,
        ref_type="ppe_transfer",
        ref_id=ref,
    )
    dest = await _find_or_create_dest_batch(
        session, tenant_id=tenant_id, source=source, to_location=dest_location
    )
    in_movement = await _write_movement(
        session,
        tenant_id=tenant_id,
        batch=dest,
        kind=KIND_TRANSFER,
        delta=quantity,
        reason=reason,
        occurred_at=when,
        ref_type="ppe_transfer",
        ref_id=ref,
    )
    return TransferResult(
        ref_id=ref,
        out_movement=out_movement,
        in_movement=in_movement,
        source_batch_id=source.id,
        dest_batch_id=dest.id,
        batch_no=source.batch_no,
        from_location=source.location,
        to_location=dest_location,
        quantity=quantity,
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/stock.py tests/api/test_ppe_stock_transfers_service.py
git commit -m "feat(p10-06): transfer_stock service — paired transfer movements + find-or-create dest"
```

---

## Task 3: Service — find-or-create merges into an existing destination batch

**Files:**
- Test: `tests/api/test_ppe_stock_transfers_service.py` (add)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_ppe_stock_transfers_service.py`:

```python
@pytest.mark.asyncio
async def test_second_transfer_merges_into_existing_dest_batch(
    sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item, source = await _item_and_batch(session, tenant.id, qty=10, location="A")

        first = await transfer_stock(
            session, tenant_id=tenant.id, source_batch_id=source.id,
            to_location="B", quantity=3,
        )
        second = await transfer_stock(
            session, tenant_id=tenant.id, source_batch_id=source.id,
            to_location="B", quantity=2,
        )
        await session.refresh(source)

        # both transfers target the SAME destination batch (no duplicate at "B")
        assert first.dest_batch_id == second.dest_batch_id
        dest_batches = (
            await session.execute(
                select(PPEStockBatch).where(
                    PPEStockBatch.tenant_id == tenant.id,
                    PPEStockBatch.item_id == item.id,
                    PPEStockBatch.location == "B",
                    PPEStockBatch.deleted_at.is_(None),
                )
            )
        ).scalars().all()

    assert len(dest_batches) == 1
    assert dest_batches[0].quantity == 5  # 3 + 2
    assert source.quantity == 5  # 10 - 3 - 2
```

- [ ] **Step 2: Run the test to verify it passes (find-or-create already implemented in Task 2)**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_service.py::test_second_transfer_merges_into_existing_dest_batch -q`
Expected: PASS. (If it FAILS with a unique-violation, the destination lookup is wrong — verify `_find_or_create_dest_batch` filters by `location == to_location` and `deleted_at IS NULL`.)

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_ppe_stock_transfers_service.py
git commit -m "test(p10-06): transfer merges into existing destination batch"
```

---

## Task 4: Service — guards (full transfer, insufficient, same-location, empty, tenant-iso)

**Files:**
- Test: `tests/api/test_ppe_stock_transfers_service.py` (add)

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_ppe_stock_transfers_service.py`:

```python
@pytest.mark.asyncio
async def test_full_transfer_empties_source(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item, source = await _item_and_batch(session, tenant.id, qty=6, location="A")
        result = await transfer_stock(
            session, tenant_id=tenant.id, source_batch_id=source.id,
            to_location="B", quantity=6,
        )
        await session.refresh(source)
        dest = (
            await session.execute(
                select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id)
            )
        ).scalar_one()
    assert source.quantity == 0  # emptied, not deleted
    assert dest.quantity == 6


@pytest.mark.asyncio
async def test_transfer_more_than_on_hand_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, source = await _item_and_batch(session, tenant.id, qty=2, location="A")
        with pytest.raises(InsufficientStockError):
            await transfer_stock(
                session, tenant_id=tenant.id, source_batch_id=source.id,
                to_location="B", quantity=5,
            )


@pytest.mark.asyncio
async def test_transfer_to_same_location_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, source = await _item_and_batch(session, tenant.id, qty=5, location="A")
        with pytest.raises(ValueError):
            await transfer_stock(
                session, tenant_id=tenant.id, source_batch_id=source.id,
                to_location="A", quantity=1,
            )


@pytest.mark.asyncio
async def test_transfer_empty_location_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        _item, source = await _item_and_batch(session, tenant.id, qty=5, location="A")
        with pytest.raises(ValueError):
            await transfer_stock(
                session, tenant_id=tenant.id, source_batch_id=source.id,
                to_location="   ", quantity=1,
            )


@pytest.mark.asyncio
async def test_transfer_unknown_source_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        with pytest.raises(StockBatchNotFound):
            await transfer_stock(
                session, tenant_id=tenant.id, source_batch_id="nope",
                to_location="B", quantity=1,
            )
```

- [ ] **Step 2: Run the tests to verify they pass (guards implemented in Task 2)**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_service.py -q`
Expected: PASS (all transfer service tests).

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_ppe_stock_transfers_service.py
git commit -m "test(p10-06): transfer guards — full/insufficient/same-location/empty/unknown"
```

---

## Task 5: Schemas — transfer + by-location DTOs

**Files:**
- Modify: `backend/app/schemas/ppe.py`
- Test: `tests/unit/test_ppe_stock_transfer_schema.py`

- [ ] **Step 1: Write the failing schema test**

Create `tests/unit/test_ppe_stock_transfer_schema.py`:

```python
"""Unit tests for PPE stock transfer schemas (P10-06)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.ppe import (
    PPEStockLevelByLocationRead,
    PPEStockTransferCreate,
    PPEStockTransferRead,
)


def test_transfer_create_valid():
    m = PPEStockTransferCreate(source_batch_id="b1", to_location="B", quantity=3)
    assert m.quantity == 3
    assert m.reason is None


def test_transfer_create_rejects_nonpositive_quantity():
    with pytest.raises(ValidationError):
        PPEStockTransferCreate(source_batch_id="b1", to_location="B", quantity=0)


def test_transfer_create_rejects_empty_location():
    with pytest.raises(ValidationError):
        PPEStockTransferCreate(source_batch_id="b1", to_location="", quantity=1)


def test_transfer_read_shape():
    from datetime import datetime, timezone

    r = PPEStockTransferRead(
        ref_id="r1",
        item_id="i1",
        item_name="Каска",
        batch_no="B-1",
        from_location="A",
        to_location="B",
        quantity=3,
        source_batch_id="s1",
        dest_batch_id="d1",
        out_movement_id="m1",
        in_movement_id="m2",
        reason=None,
        occurred_at=datetime.now(tz=timezone.utc),
    )
    assert r.from_location == "A"
    assert r.to_location == "B"


def test_level_by_location_read_shape():
    r = PPEStockLevelByLocationRead(
        item_id="i1", item_name="Каска", location="A", quantity=7, batch_count=2
    )
    assert r.location == "A"
    assert r.quantity == 7
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/unit/test_ppe_stock_transfer_schema.py -q`
Expected: FAIL — `ImportError` (schemas not defined).

- [ ] **Step 3: Add the schemas**

In `backend/app/schemas/ppe.py`, near the other stock schemas (after `PPEStockLevelPage`, around line 252). `Field`, `datetime`, `BaseSchema` are already imported in this module:

```python
class PPEStockTransferCreate(BaseSchema):
    source_batch_id: str
    to_location: str = Field(min_length=1, max_length=255)
    quantity: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)
    occurred_at: datetime | None = None


class PPEStockTransferRead(BaseSchema):
    ref_id: str
    item_id: str
    item_name: str
    batch_no: str
    from_location: str | None
    to_location: str
    quantity: int
    source_batch_id: str
    dest_batch_id: str
    out_movement_id: str
    in_movement_id: str
    reason: str | None
    occurred_at: datetime


class PPEStockTransferPage(BaseSchema):
    items: list[PPEStockTransferRead]
    total: int


class PPEStockLevelByLocationRead(BaseSchema):
    item_id: str
    item_name: str
    location: str | None
    quantity: int
    batch_count: int


class PPEStockLevelByLocationPage(BaseSchema):
    items: list[PPEStockLevelByLocationRead]
    total: int
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/unit/test_ppe_stock_transfer_schema.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/ppe.py tests/unit/test_ppe_stock_transfer_schema.py
git commit -m "feat(p10-06): stock transfer + by-location schemas"
```

---

## Task 6: API — `POST /ppe/stock/transfers`

**Files:**
- Modify: `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_stock_transfers_api.py`

- [ ] **Step 1: Write the failing API test**

Create `tests/api/test_ppe_stock_transfers_api.py`:

```python
"""API contract for PPE stock transfers (P10-06)."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _seed_item(async_client: AsyncClient, headers, *, name="Каска") -> str:
    resp = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


async def _seed_batch(async_client, headers, item_id, *, no="B-1", qty=10, location="A") -> str:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": no, "quantity": qty, "location": location},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_transfer_moves_stock_between_locations(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 3},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    body = resp.json()
    assert body["from_location"] == "A"
    assert body["to_location"] == "B"
    assert body["quantity"] == 3
    assert body["item_id"] == item_id

    # item on-hand unchanged (out + in = 0)
    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    row = next(r for r in levels.json()["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 10


@pytest.mark.asyncio
async def test_transfer_insufficient_returns_400(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=2, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 5},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.text


@pytest.mark.asyncio
async def test_transfer_same_location_returns_400(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=5, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "A", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST, resp.text


@pytest.mark.asyncio
async def test_transfer_zero_quantity_returns_422(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=5, location="A")

    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 0},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_transfer_unknown_source_returns_404(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": "nope", "to_location": "B", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_api.py -q`
Expected: FAIL — route returns 404 for a path that does not exist / test setup errors.

- [ ] **Step 3: Add the imports and the POST route**

In `backend/app/api/routes/ppe.py`:

1. Extend the `from app.modules.ppe.stock import (...)` block (around line 57) to include `KIND_TRANSFER` and `transfer_stock`:

```python
from app.modules.ppe.stock import (
    InsufficientStockError,
    StockBatchNotFound,
    KIND_TRANSFER,
    transfer_stock,
    # ...existing imports (record_movement, deplete_for_issue, compute_shortages, etc.)
)
```

2. Extend the schema import block to include the new schemas:

```python
    PPEStockTransferCreate,
    PPEStockTransferRead,
    PPEStockTransferPage,
    PPEStockLevelByLocationRead,
    PPEStockLevelByLocationPage,
```

3. Add the POST route after `list_stock_movements` (after line ~1172):

```python
@router.post(
    "/stock/transfers",
    response_model=PPEStockTransferRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("create", "ppe_stock_transfer")
async def create_stock_transfer(
    payload: PPEStockTransferCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPEStockTransferRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        result = await transfer_stock(
            session,
            tenant_id=tenant.id,
            source_batch_id=payload.source_batch_id,
            to_location=payload.to_location,
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
    except StaleDataError as exc:
        raise _ppe_conflict("stock batch was modified concurrently") from exc

    item_name = (
        await session.execute(
            select(PPEItem.name).where(PPEItem.id == result.out_movement.item_id)
        )
    ).scalar_one_or_none() or ""
    return PPEStockTransferRead(
        ref_id=result.ref_id,
        item_id=result.out_movement.item_id,
        item_name=item_name,
        batch_no=result.batch_no,
        from_location=result.from_location,
        to_location=result.to_location,
        quantity=result.quantity,
        source_batch_id=result.source_batch_id,
        dest_batch_id=result.dest_batch_id,
        out_movement_id=result.out_movement.id,
        in_movement_id=result.in_movement.id,
        reason=result.out_movement.reason,
        occurred_at=result.out_movement.occurred_at,
    )
```

(`select`, `PPEItem`, `HTTPException`, `status`, `_ppe_bad_request`, `_ppe_conflict`, `StaleDataError`, `WarehouseFeatureGate`, `EditorAccess`, `TenantDep`, `SessionDep`, `@audit_operation`, `TenantContextValidator` are all already imported/used in this module.)

- [ ] **Step 4: Run the test to verify it passes**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_api.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/ppe.py tests/api/test_ppe_stock_transfers_api.py
git commit -m "feat(p10-06): POST /ppe/stock/transfers route"
```

---

## Task 7: API — `GET /ppe/stock/transfers` (history, pair grouping, item filter, ETag)

**Files:**
- Modify: `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_stock_transfers_api.py` (add)

**Scope note:** history is filtered by `item_id` only in this slice. `location` filter is deferred (the "by location" view is served by `GET /stock/levels/by-location`); a transfer's from/to locations live on the referenced batches, not on the movement rows, so a DB-level location filter would require a join that is out of scope here. Recorded in the docs task.

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_ppe_stock_transfers_api.py`:

```python
@pytest.mark.asyncio
async def test_list_transfers_groups_pairs(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10, location="A")

    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 3},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "C", "quantity": 2},
        headers=headers,
    )

    resp = await async_client.get("/api/v1/ppe/stock/transfers", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 2  # two pairs, not four journal rows
    tos = {row["to_location"] for row in body["items"]}
    assert tos == {"B", "C"}
    for row in body["items"]:
        assert row["from_location"] == "A"
        assert row["batch_no"] == "B-1"
        assert row["quantity"] in (2, 3)

    # ETag round-trip → 304
    etag = resp.headers.get("etag")
    assert etag
    cached = await async_client.get(
        "/api/v1/ppe/stock/transfers", headers={**headers, "if-none-match": etag}
    )
    assert cached.status_code == status.HTTP_304_NOT_MODIFIED


@pytest.mark.asyncio
async def test_list_transfers_filter_by_item(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item1 = await _seed_item(async_client, headers, name="Каска")
    item2 = await _seed_item(async_client, headers, name="Перчатки")
    b1 = await _seed_batch(async_client, headers, item1, no="B-1", qty=10, location="A")
    b2 = await _seed_batch(async_client, headers, item2, no="B-2", qty=10, location="A")
    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": b1, "to_location": "B", "quantity": 3},
        headers=headers,
    )
    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": b2, "to_location": "B", "quantity": 3},
        headers=headers,
    )

    resp = await async_client.get(
        "/api/v1/ppe/stock/transfers", params={"item_id": item1}, headers=headers
    )
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["item_id"] == item1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_api.py::test_list_transfers_groups_pairs -q`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Add the GET route**

In `backend/app/api/routes/ppe.py`, after `create_stock_transfer`:

```python
@router.get(
    "/stock/transfers",
    response_model=PPEStockTransferPage,
    dependencies=[WarehouseFeatureGate],
)
async def list_stock_transfers(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    item_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEStockTransferPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    # Page over transfer PAIRS (ref_id), newest first, so a pair never splits
    # across a page boundary.
    pair_filter = [
        PPEStockMovement.tenant_id == tenant.id,
        PPEStockMovement.kind == KIND_TRANSFER,
    ]
    if item_id:
        pair_filter.append(PPEStockMovement.item_id == item_id)

    pair_stmt = (
        select(
            PPEStockMovement.ref_id.label("ref"),
            func.max(PPEStockMovement.occurred_at).label("occ"),
        )
        .where(*pair_filter)
        .group_by(PPEStockMovement.ref_id)
    )
    total = (
        await session.execute(select(func.count()).select_from(pair_stmt.subquery()))
    ).scalar_one()

    page_rows = (
        await session.execute(
            pair_stmt.order_by(
                func.max(PPEStockMovement.occurred_at).desc(),
                PPEStockMovement.ref_id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()
    page_refs = [r.ref for r in page_rows]

    movements: list[PPEStockMovement] = []
    if page_refs:
        movements = list(
            (
                await session.execute(
                    select(PPEStockMovement).where(
                        PPEStockMovement.tenant_id == tenant.id,
                        PPEStockMovement.kind == KIND_TRANSFER,
                        PPEStockMovement.ref_id.in_(page_refs),
                    )
                )
            )
            .scalars()
            .all()
        )

    # resolve batch (for locations + batch_no) and item names in fixed queries
    batch_ids = {m.batch_id for m in movements if m.batch_id}
    batch_map: dict[str, PPEStockBatch] = {}
    if batch_ids:
        batch_map = {
            b.id: b
            for b in (
                await session.execute(
                    select(PPEStockBatch).where(PPEStockBatch.id.in_(batch_ids))
                )
            )
            .scalars()
            .all()
        }
    item_ids = {m.item_id for m in movements}
    names: dict[str, str] = {}
    if item_ids:
        names = {
            iid: name
            for iid, name in (
                await session.execute(
                    select(PPEItem.id, PPEItem.name).where(PPEItem.id.in_(item_ids))
                )
            ).all()
        }

    grouped: dict[str, list[PPEStockMovement]] = {}
    for m in movements:
        grouped.setdefault(m.ref_id, []).append(m)

    items: list[PPEStockTransferRead] = []
    for ref in page_refs:  # preserve newest-first order
        pair = grouped.get(ref, [])
        out = next((m for m in pair if m.quantity_delta < 0), None)
        inc = next((m for m in pair if m.quantity_delta > 0), None)
        if out is None or inc is None:
            continue  # defensive: a half-pair should never happen
        out_batch = batch_map.get(out.batch_id or "")
        in_batch = batch_map.get(inc.batch_id or "")
        items.append(
            PPEStockTransferRead(
                ref_id=ref,
                item_id=out.item_id,
                item_name=names.get(out.item_id, ""),
                batch_no=out_batch.batch_no if out_batch else "",
                from_location=out_batch.location if out_batch else None,
                to_location=in_batch.location if in_batch else "",
                quantity=inc.quantity_delta,
                source_batch_id=out.batch_id or "",
                dest_batch_id=inc.batch_id or "",
                out_movement_id=out.id,
                in_movement_id=inc.id,
                reason=out.reason,
                occurred_at=out.occurred_at,
            )
        )

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("item", item_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PPEStockTransferPage(items=items, total=total)
```

(`compute_list_etag`, `apply_etag_response_headers`, `build_not_modified_headers`, `Request`, `Response`, `Query`, `func`, `PPEStockBatch`, `PPEStockMovement` are already imported/used in this module — see `list_stock_movements`.)

**Note on `compute_list_etag`:** it hashes the `items`. If it requires ORM rows rather than Pydantic models, mirror exactly how `list_stock_movements` calls it. If passing Pydantic models is unsupported, build the etag from a stable list of tuples instead (e.g. `[(i.ref_id, i.quantity, i.to_location) for i in items]`) — verify against the running behavior of `list_stock_movements` before finalizing.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_api.py -q`
Expected: PASS (all transfer API tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/ppe.py tests/api/test_ppe_stock_transfers_api.py
git commit -m "feat(p10-06): GET /ppe/stock/transfers history (pair grouping + ETag)"
```

---

## Task 8: API — `GET /ppe/stock/levels/by-location`

**Files:**
- Modify: `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_stock_transfers_api.py` (add)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_ppe_stock_transfers_api.py`:

```python
@pytest.mark.asyncio
async def test_levels_by_location_reflects_transfer(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    batch_id = await _seed_batch(async_client, headers, item_id, qty=10, location="A")

    await async_client.post(
        "/api/v1/ppe/stock/transfers",
        json={"source_batch_id": batch_id, "to_location": "B", "quantity": 4},
        headers=headers,
    )

    resp = await async_client.get("/api/v1/ppe/stock/levels/by-location", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    rows = {r["location"]: r for r in resp.json()["items"] if r["item_id"] == item_id}
    assert rows["A"]["quantity"] == 6
    assert rows["B"]["quantity"] == 4
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_api.py::test_levels_by_location_reflects_transfer -q`
Expected: FAIL — 404 (route missing).

- [ ] **Step 3: Add the route**

In `backend/app/api/routes/ppe.py`, after `list_stock_levels` (after line ~1043):

```python
@router.get(
    "/stock/levels/by-location",
    response_model=PPEStockLevelByLocationPage,
    dependencies=[WarehouseFeatureGate],
)
async def list_stock_levels_by_location(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PPEStockLevelByLocationPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    agg_stmt = (
        select(
            PPEStockBatch.item_id,
            PPEStockBatch.location,
            func.coalesce(func.sum(PPEStockBatch.quantity), 0),
            func.count(PPEStockBatch.id),
        )
        .where(
            PPEStockBatch.tenant_id == tenant.id,
            PPEStockBatch.deleted_at.is_(None),
        )
        .group_by(PPEStockBatch.item_id, PPEStockBatch.location)
    )
    rows = (await session.execute(agg_stmt)).all()

    names: dict[str, str] = {}
    item_ids = [row[0] for row in rows]
    if item_ids:
        names = {
            iid: name
            for iid, name in (
                await session.execute(
                    select(PPEItem.id, PPEItem.name).where(PPEItem.id.in_(item_ids))
                )
            ).all()
        }

    items = [
        PPEStockLevelByLocationRead(
            item_id=row[0],
            item_name=names.get(row[0], ""),
            location=row[1],
            quantity=int(row[2] or 0),
            batch_count=int(row[3] or 0),
        )
        for row in rows
    ]
    return PPEStockLevelByLocationPage(items=items, total=len(items))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_api.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full backend transfer regression + adjacent stock suites**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_service.py tests/api/test_ppe_stock_transfers_api.py tests/unit/test_ppe_stock_transfer_schema.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_warehouse_api.py backend/tests/test_wa07_ppe_stock_batch_location_migration.py -q`
Expected: PASS (no regressions in adjacent stock tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/ppe.py tests/api/test_ppe_stock_transfers_api.py
git commit -m "feat(p10-06): GET /ppe/stock/levels/by-location"
```

---

## Task 9: Frontend — `warehouseApi` transfer + by-location methods

**Files:**
- Modify: `frontend/src/api/warehouse.ts`
- Test: `frontend/src/__tests__/WarehousePage.test.tsx` (extend mock; full render test in Task 10)

- [ ] **Step 1: Add DTOs and methods**

In `frontend/src/api/warehouse.ts`, add types after `StockMovementDto` (near line 35):

```typescript
export type StockTransferDto = {
  ref_id: string;
  item_id: string;
  item_name: string;
  batch_no: string;
  from_location?: string | null;
  to_location: string;
  quantity: number;
  source_batch_id: string;
  dest_batch_id: string;
  out_movement_id: string;
  in_movement_id: string;
  reason?: string | null;
  occurred_at: string;
};

export type CreateTransferInput = {
  source_batch_id: string;
  to_location: string;
  quantity: number;
  reason?: string | null;
};

export type StockLevelByLocationDto = {
  item_id: string;
  item_name: string;
  location?: string | null;
  quantity: number;
  batch_count: number;
};
```

Add methods inside the `warehouseApi` object (after `createMovement`, before `listShortages`):

```typescript
  async listTransfers(params?: { item_id?: string }): Promise<StockTransferDto[]> {
    const response = await apiClient.get<PageResponse<StockTransferDto>>("/ppe/stock/transfers", {
      params: { limit: 50, offset: 0, ...(params ?? {}) }
    });
    return response.data.items ?? [];
  },
  async createTransfer(input: CreateTransferInput): Promise<StockTransferDto> {
    const response = await apiClient.post<StockTransferDto>("/ppe/stock/transfers", input);
    return response.data;
  },
  async listLevelsByLocation(): Promise<StockLevelByLocationDto[]> {
    const response = await apiClient.get<PageResponse<StockLevelByLocationDto>>(
      "/ppe/stock/levels/by-location"
    );
    return response.data.items ?? [];
  },
```

- [ ] **Step 2: Typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: exit 0 (no type errors).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/warehouse.ts
git commit -m "feat(p10-06): warehouseApi transfer + by-location methods"
```

---

## Task 10: Frontend — "Перемещения между локациями" section on WarehousePage

**Files:**
- Modify: `frontend/src/pages/warehouse/WarehousePage.tsx`
- Test: `frontend/src/__tests__/WarehousePage.test.tsx`

- [ ] **Step 1: Write the failing render/interaction test**

Open `frontend/src/__tests__/WarehousePage.test.tsx`, inspect how `warehouseApi` is mocked (it mocks each method with `vi.fn()`). Add `listTransfers`, `createTransfer`, `listLevelsByLocation` to the mock (default resolve `[]`), then add:

```typescript
it("creates a stock transfer and shows it in the history", async () => {
  const user = userEvent.setup();
  // adjust these mock handles to match the file's existing mock style
  (warehouseApi.listBatches as Mock).mockResolvedValue([
    { id: "b1", item_id: "i1", batch_no: "B-1", quantity: 10, location: "A",
      created_at: "", updated_at: "" },
  ]);
  (warehouseApi.listLevelsByLocation as Mock).mockResolvedValue([
    { item_id: "i1", item_name: "Каска", location: "A", quantity: 10, batch_count: 1 },
  ]);
  (warehouseApi.listTransfers as Mock).mockResolvedValue([]);
  (warehouseApi.createTransfer as Mock).mockResolvedValue({
    ref_id: "r1", item_id: "i1", item_name: "Каска", batch_no: "B-1",
    from_location: "A", to_location: "B", quantity: 3,
    source_batch_id: "b1", dest_batch_id: "d1",
    out_movement_id: "m1", in_movement_id: "m2", reason: null,
    occurred_at: new Date().toISOString(),
  });

  render(<WarehousePage />);
  await screen.findByText(/Перемещения между локациями/i);

  await user.type(screen.getByLabelText(/Партия-источник/i), "b1");
  await user.type(screen.getByLabelText(/Куда \(локация\)/i), "B");
  await user.clear(screen.getByLabelText(/Количество/i));
  await user.type(screen.getByLabelText(/Количество/i), "3");
  await user.click(screen.getByRole("button", { name: /Перенести/i }));

  await waitFor(() => expect(warehouseApi.createTransfer).toHaveBeenCalledWith({
    source_batch_id: "b1", to_location: "B", quantity: 3, reason: null,
  }));
});
```

(Match imports — `render`, `screen`, `waitFor`, `userEvent`, `Mock` — to the file's existing top-of-file imports and the existing mock setup for `warehouseApi`. If the file mocks `@/api/warehouse` with an inline factory, add the three new methods there.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `npm --prefix frontend run test -- WarehousePage`
Expected: FAIL — section/labels not found.

- [ ] **Step 3: Implement the section**

In `frontend/src/pages/warehouse/WarehousePage.tsx`:

1. Extend the imports from `@/api/warehouse` to include `StockTransferDto`, `StockLevelByLocationDto`, `CreateTransferInput`.
2. Add state (near the other `useState` declarations, ~line 38):

```typescript
  const [transfers, setTransfers] = useState<StockTransferDto[]>([]);
  const [levelsByLoc, setLevelsByLoc] = useState<StockLevelByLocationDto[]>([]);
  const [transferForm, setTransferForm] = useState({
    source_batch_id: "",
    to_location: "",
    quantity: "1",
    reason: "",
  });
  const [transferSubmitting, setTransferSubmitting] = useState(false);
```

3. Add the two loaders to the `Promise.all([...])` in the load effect (~line 45):

```typescript
        warehouseApi.listTransfers(),
        warehouseApi.listLevelsByLocation(),
```

and destructure/assign them to `setTransfers(...)` / `setLevelsByLoc(...)` alongside the existing setters (keep array order aligned with the destructuring).

4. Add a submit handler (near `handleCreateMovement`, ~line 60):

```typescript
  const handleCreateTransfer = async (e: React.FormEvent) => {
    e.preventDefault();
    setTransferSubmitting(true);
    setError(null);
    try {
      const body: CreateTransferInput = {
        source_batch_id: transferForm.source_batch_id.trim(),
        to_location: transferForm.to_location.trim(),
        quantity: Number(transferForm.quantity),
        reason: transferForm.reason.trim() || null,
      };
      await warehouseApi.createTransfer(body);
      setTransferForm({ source_batch_id: "", to_location: "", quantity: "1", reason: "" });
      const [t, l] = await Promise.all([
        warehouseApi.listTransfers(),
        warehouseApi.listLevelsByLocation(),
      ]);
      setTransfers(t);
      setLevelsByLoc(l);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setTransferSubmitting(false);
    }
  };

  const knownLocations = useMemo(
    () => Array.from(new Set(levelsByLoc.map((l) => l.location).filter(Boolean))) as string[],
    [levelsByLoc]
  );
```

5. Render a new `Card` section (place it after the "Движения" section, mirroring its markup — reuse the existing `Card`, `CardHeader`, `CardTitle`, `CardContent`, `Table*`, `Input`, `Button`, `Label` components already imported in this file). Key requirements the test relies on:
   - A heading with the text `Перемещения между локациями`.
   - Inputs with accessible labels: `Партия-источник` (`source_batch_id`), `Куда (локация)` (`to_location`, with a `<datalist>` populated from `knownLocations`), `Количество` (`quantity`, `type="number"`, `min="1"`), and an optional `Причина` (`reason`).
   - A submit button labelled `Перенести` (disabled while `transferSubmitting`), calling `handleCreateTransfer`.
   - A history table listing `transfers` with columns: позиция (`item_name`), партия (`batch_no`), маршрут (`from_location → to_location`), количество (`quantity`), когда (`occurred_at`).

Example section skeleton (adapt component names/props to the ones this file already uses):

```tsx
<Card>
  <CardHeader>
    <CardTitle className="text-base">Перемещения между локациями</CardTitle>
  </CardHeader>
  <CardContent className="space-y-4">
    <form onSubmit={handleCreateTransfer} className="grid gap-3 sm:grid-cols-2">
      <div>
        <Label htmlFor="tr-src">Партия-источник</Label>
        <Input id="tr-src" value={transferForm.source_batch_id}
          onChange={(e) => setTransferForm((f) => ({ ...f, source_batch_id: e.target.value }))} />
      </div>
      <div>
        <Label htmlFor="tr-to">Куда (локация)</Label>
        <Input id="tr-to" list="tr-locations" value={transferForm.to_location}
          onChange={(e) => setTransferForm((f) => ({ ...f, to_location: e.target.value }))} />
        <datalist id="tr-locations">
          {knownLocations.map((loc) => <option key={loc} value={loc} />)}
        </datalist>
      </div>
      <div>
        <Label htmlFor="tr-qty">Количество</Label>
        <Input id="tr-qty" type="number" min="1" value={transferForm.quantity}
          onChange={(e) => setTransferForm((f) => ({ ...f, quantity: e.target.value }))} />
      </div>
      <div>
        <Label htmlFor="tr-reason">Причина</Label>
        <Input id="tr-reason" value={transferForm.reason}
          onChange={(e) => setTransferForm((f) => ({ ...f, reason: e.target.value }))} />
      </div>
      <div className="sm:col-span-2">
        <Button type="submit" disabled={transferSubmitting}>Перенести</Button>
      </div>
    </form>
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Позиция</TableHead>
          <TableHead>Партия</TableHead>
          <TableHead>Маршрут</TableHead>
          <TableHead>Кол-во</TableHead>
          <TableHead>Когда</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {transfers.map((t) => (
          <TableRow key={t.ref_id}>
            <TableCell>{t.item_name}</TableCell>
            <TableCell>{t.batch_no}</TableCell>
            <TableCell>{(t.from_location ?? "—")} → {t.to_location}</TableCell>
            <TableCell>{t.quantity}</TableCell>
            <TableCell>{new Date(t.occurred_at).toLocaleString()}</TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  </CardContent>
</Card>
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `npm --prefix frontend run test -- WarehousePage`
Expected: PASS.

- [ ] **Step 5: Typecheck + build**

Run: `npm --prefix frontend run typecheck && npm --prefix frontend run build`
Expected: both exit 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/warehouse/WarehousePage.tsx frontend/src/__tests__/WarehousePage.test.tsx
git commit -m "feat(p10-06): WarehousePage — transfers between locations section"
```

---

## Task 11: Gates — OpenAPI baseline, lint, PG16 gate, docs, handoff

**Files:**
- Modify: `docs/stabilization/openapi_routes_baseline.json`
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`
- Modify: `CHANGELOG.md`
- Modify: `AI_IMPLEMENTATION_REPORT.md`

- [ ] **Step 1: Lint/format the backend changes**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m ruff check backend/app/modules/ppe/stock.py backend/app/api/routes/ppe.py backend/app/schemas/ppe.py backend/app/models/ppe.py && C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m black --check backend/app/modules/ppe/stock.py backend/app/api/routes/ppe.py backend/app/schemas/ppe.py backend/app/models/ppe.py tests/api/test_ppe_stock_transfers_service.py tests/api/test_ppe_stock_transfers_api.py tests/unit/test_ppe_stock_transfer_schema.py`
Expected: ruff clean; black reports "would reformat" nowhere (if it does, run without `--check` and re-commit).

- [ ] **Step 2: Re-snapshot the OpenAPI baseline**

Run: `$env:PYTHONPATH="backend"; C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe scripts/ci/check_openapi_snapshot.py --snapshot`
Then verify the diff is a clean additive: exactly the 3 new routes (`POST /api/v1/ppe/stock/transfers`, `GET /api/v1/ppe/stock/transfers`, `GET /api/v1/ppe/stock/levels/by-location`) and the new schemas.
Run: `$env:PYTHONPATH="backend"; C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe scripts/ci/check_openapi_snapshot.py`
Expected: compare EXIT 0. Record the new counts (was 817/660 → expect 820/~665).

- [ ] **Step 3: PG16 migration gate (round-trip for wa07)**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe scripts/ci/local_gate.py --db-only`
Expected: alembic upgrade (incl. wa07) + downgrade round-trip green; single head is `20260704_wa07_ppe_stock_batch_location_unique`.
If PG16 is not available locally, note the mismatch in the handoff and mark this as CI-verified (per repo policy) — do **not** abort.

- [ ] **Step 4: Update roadmap**

In `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, in the P10-06 row: append shipped-prose "перемещения между локациями (частичный split, `wa07`, `POST/GET /stock/transfers`, `GET /stock/levels/by-location`)" and remove "перемещения между локациями" from the "Остаётся" list. Note the deferred `location` filter on transfer history as a follow-up.

- [ ] **Step 5: Update CHANGELOG**

In `CHANGELOG.md`, add a `2026-07-04` entry: "P10-06 СИЗ склад — перемещения запаса между локациями (частичный перенос через пару transfer-проводок, find-or-create партии-приёмника, миграция wa07 расширяет уникальный ключ партии локацией; новые роуты `POST/GET /ppe/stock/transfers`, `GET /ppe/stock/levels/by-location`)."

- [ ] **Step 6: Update the handoff journal**

Prepend a new `## Last Agent Handoff (2026-07-04, P10-06 СИЗ СКЛАД — ПЕРЕМЕЩЕНИЯ МЕЖДУ ЛОКАЦИЯМИ ...)` block to `AI_IMPLEMENTATION_REPORT.md` covering: what shipped, the `wa07` unique-key change + `NULLS NOT DISTINCT`, the paired-movement invariant, deferred `location` filter, new OpenAPI counts, verification results (with the Py version mismatch noted), and the next exact step (следующий срез P10-06 — поставщики; или P10-03 медосмотры / P10-07 report-builder UI).

- [ ] **Step 7: Full slice regression + commit**

Run: `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest tests/api/test_ppe_stock_transfers_service.py tests/api/test_ppe_stock_transfers_api.py tests/unit/test_ppe_stock_transfer_schema.py backend/tests/test_wa07_ppe_stock_batch_location_migration.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_warehouse_api.py tests/api/test_ppe_inventory_count_api.py -q`
Expected: PASS. Then:

```bash
git add docs/stabilization/openapi_routes_baseline.json docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md CHANGELOG.md AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(p10-06): roadmap + changelog + OpenAPI baseline + handoff for stock transfers"
```

---

## Self-Review

**1. Spec coverage:**
- Layer 1 (model unique key) → Task 1. ✓
- Layer 2 (`wa07` migration) → Task 1. ✓
- Layer 3 (`transfer_stock`, `KIND_TRANSFER`, find-or-create, pair) → Tasks 2-4. ✓
- Layer 4 (schemas) → Task 5. ✓
- Layer 5 (3 API routes) → Tasks 6-8. ✓
- Layer 6 (frontend) → Tasks 9-10. ✓
- Verification/gates (OpenAPI, ruff/black, PG16, docs, handoff) → Task 11. ✓
- **Deviation from spec (recorded):** `GET /stock/transfers` `location` filter deferred (from/to live on batches, not movement rows) — noted in Task 7 and Task 11 step 4. Per-location view is served by `GET /stock/levels/by-location`. `item_id` filter retained.
- **Deviation from spec (improvement):** in `transfer_stock` the source depletion (`-q`) runs before destination find-or-create, so an insufficient balance raises before any dest batch is created (rollback-safe either way). Spec's anti-грабли still hold.

**2. Placeholder scan:** no TBD/TODO; every code step shows full code; every run step shows the command + expected result. The `compute_list_etag` note in Task 7 is a verification instruction (mirror `list_stock_movements`), not a placeholder.

**3. Type consistency:** `transfer_stock` / `TransferResult` (fields `ref_id`, `out_movement`, `in_movement`, `source_batch_id`, `dest_batch_id`, `batch_no`, `from_location`, `to_location`, `quantity`) are consistent between Task 2 (definition), Task 6 (POST route consumes them), and Task 7 (GET rebuilds equivalent rows). DTO field names (`PPEStockTransferRead`, `PPEStockLevelByLocationRead`) match between Task 5 (schema), Tasks 6-8 (routes), and Task 9 (frontend DTOs). `KIND_TRANSFER = "transfer"` used identically in service, GET route, and frontend union type.
