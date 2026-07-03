# P10-06 СИЗ склад — Мин-остаток + прогноз дефицита — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-item `min_stock` threshold and a velocity-based shortage report (`GET /ppe/stock/shortages`) on top of the honest PPE warehouse balance, surfaced on `WarehousePage`.

**Architecture:** One additive column (`ppeitem.min_stock`, migration `wa05`). A pure forecast function (`project_shortage`) + an aggregation service (`compute_shortages`) in the existing warehouse engine `backend/app/modules/ppe/stock.py`. A read-only endpoint mirroring `/stock/levels` (no ETag — computed aggregate). Frontend section on `WarehousePage`. Everything behind the `warehouse` feature flag.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.x async / Alembic / pytest-asyncio; React 18 / TypeScript / Vitest.

**Spec:** `docs/superpowers/specs/2026-07-03-p10-06-ppe-min-stock-shortage-design.md`

**Conventions (verified against repo):**
- Run backend tests from repo root: `python -m pytest <path> -q` (pyproject sets `pythonpath = ["backend", "."]`; use the repo venv python, e.g. `.venv/Scripts/python.exe` on Windows).
- Run frontend tests: `npm --prefix frontend run test -- <name>`; typecheck: `npm --prefix frontend run typecheck`.
- API tests seed via `data_factory.ensure_tenant(session=...)` + `make_auth_headers(RoleEnum.ADMIN)` + `async_client`; item/batch created through the real API (`_seed_item` / `_seed_batch`).
- Current alembic head on the PPE line: `20260702_wa04_ppe_stock_movement` (wa05 chains from it).

---

## File Structure

- `backend/app/models/ppe.py` — add `min_stock` to `PPEItem` (Task 1).
- `backend/app/migrations/versions/20260703_wa05_ppeitem_min_stock.py` — additive column (Task 1).
- `backend/app/modules/ppe/stock.py` — `ShortageProjection` + `project_shortage` (Task 2); `ShortageRow` + `compute_shortages` (Task 3).
- `backend/app/schemas/ppe.py` — `min_stock` on `PPEItemCreate/Update/Read`; `PPEStockShortageRead` + `PPEStockShortagePage` (Tasks 4, 5).
- `backend/app/api/routes/ppe.py` — wire `min_stock` into `create_item` (Task 4); `GET /stock/shortages` (Task 5).
- `frontend/src/api/warehouse.ts` — `PPEStockShortageDto` + `listShortages` (Task 6).
- `frontend/src/pages/warehouse/WarehousePage.tsx` — shortage section + `min_stock` in item form (Task 6).
- Tests: `backend/tests/test_wa05_ppeitem_min_stock_migration.py`, `tests/unit/test_ppe_shortage_projection.py`, `tests/api/test_ppe_shortage_service.py`, `tests/api/test_ppe_shortage_api.py`, `frontend/src/__tests__/WarehousePage.test.tsx`.
- Docs: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, `CHANGELOG.md`, `AI_IMPLEMENTATION_REPORT.md`, OpenAPI snapshot (Task 7).

---

## Task 1: Additive migration `wa05` + `PPEItem.min_stock` column

**Files:**
- Modify: `backend/app/models/ppe.py:140-158` (PPEItem class, add field)
- Create: `backend/app/migrations/versions/20260703_wa05_ppeitem_min_stock.py`
- Test: `backend/tests/test_wa05_ppeitem_min_stock_migration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_wa05_ppeitem_min_stock_migration.py
"""wa05 adds an additive ppeitem.min_stock column (P10-06)."""
from __future__ import annotations

import pathlib

MIGRATION = pathlib.Path(
    "backend/app/migrations/versions/20260703_wa05_ppeitem_min_stock.py"
)


def test_migration_file_exists():
    assert MIGRATION.exists(), "wa05 migration missing"


def test_migration_is_additive_add_column():
    text = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260703_wa05_ppeitem_min_stock"' in text
    assert 'down_revision = "20260702_wa04_ppe_stock_movement"' in text
    # additive: adds the column, drops it on downgrade, no table drops
    assert 'op.add_column("ppeitem"' in text
    assert '"min_stock"' in text
    assert 'server_default="0"' in text
    assert 'op.drop_column("ppeitem", "min_stock")' in text
    assert "drop_table" not in text


def test_model_has_min_stock():
    from app.models.ppe import PPEItem

    assert "min_stock" in PPEItem.__table__.columns
    assert PPEItem.__table__.columns["min_stock"].nullable is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_wa05_ppeitem_min_stock_migration.py -q`
Expected: FAIL (migration file missing; `min_stock` not in `PPEItem.__table__`).

- [ ] **Step 3: Add the model column**

In `backend/app/models/ppe.py`, inside `class PPEItem` (after `default_wear_days`, before `metadata_json`), add:

```python
    min_stock: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
```

- [ ] **Step 4: Create the migration**

```python
# backend/app/migrations/versions/20260703_wa05_ppeitem_min_stock.py
"""wa05: additive ppeitem.min_stock column (P10-06 min-stock threshold).

Revision ID: 20260703_wa05_ppeitem_min_stock
Revises: 20260702_wa04_ppe_stock_movement
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260703_wa05_ppeitem_min_stock"
down_revision = "20260702_wa04_ppe_stock_movement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ppeitem",
        sa.Column("min_stock", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("ppeitem", "min_stock")
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_wa05_ppeitem_min_stock_migration.py -q`
Expected: PASS (3 tests).

- [ ] **Step 6: Verify migration applies (PG16 gate is authoritative; local SQLite smoke first)**

Run: `python -m pytest backend/tests/test_wa04_ppe_stock_movement_migration.py -q`
Expected: PASS (regression — confirms the migration chain still resolves with wa05 appended).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/ppe.py backend/app/migrations/versions/20260703_wa05_ppeitem_min_stock.py backend/tests/test_wa05_ppeitem_min_stock_migration.py
git commit -m "feat(p10-06): additive migration wa05 for ppeitem.min_stock"
```

---

## Task 2: Pure forecast function `project_shortage`

**Files:**
- Modify: `backend/app/modules/ppe/stock.py` (add after `allocate_fifo`, ~line 70)
- Test: `tests/unit/test_ppe_shortage_projection.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_ppe_shortage_projection.py
"""Pure shortage projection — no DB (P10-06)."""
from __future__ import annotations

from app.modules.ppe.stock import ShortageProjection, project_shortage


def test_above_threshold_not_below():
    p = project_shortage(on_hand=100, min_stock=20, avg_daily=1.0)
    assert p.below_threshold is False
    assert p.deficit == 0
    assert p.days_to_depletion == 100.0
    assert p.days_to_threshold == 80.0


def test_below_threshold_sets_deficit_and_zero_days_to_threshold():
    p = project_shortage(on_hand=5, min_stock=20, avg_daily=1.0)
    assert p.below_threshold is True
    assert p.deficit == 15
    assert p.days_to_depletion == 5.0
    assert p.days_to_threshold == 0.0


def test_at_threshold_is_not_below():
    p = project_shortage(on_hand=20, min_stock=20, avg_daily=2.0)
    assert p.below_threshold is False
    assert p.deficit == 0
    assert p.days_to_threshold == 0.0


def test_zero_consumption_gives_none_days():
    p = project_shortage(on_hand=5, min_stock=20, avg_daily=0.0)
    assert p.below_threshold is True
    assert p.deficit == 15
    assert p.days_to_depletion is None
    assert p.days_to_threshold is None


def test_zero_on_hand_below_with_zero_days():
    p = project_shortage(on_hand=0, min_stock=10, avg_daily=2.0)
    assert p.below_threshold is True
    assert p.deficit == 10
    assert p.days_to_depletion == 0.0


def test_min_stock_zero_never_below():
    p = project_shortage(on_hand=0, min_stock=0, avg_daily=1.0)
    assert p.below_threshold is False
    assert p.deficit == 0


def test_returns_frozen_dataclass():
    p = project_shortage(on_hand=1, min_stock=1, avg_daily=0.0)
    assert isinstance(p, ShortageProjection)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/unit/test_ppe_shortage_projection.py -q`
Expected: FAIL with `ImportError: cannot import name 'project_shortage'`.

- [ ] **Step 3: Implement the pure function**

In `backend/app/modules/ppe/stock.py`, after `allocate_fifo` (line 70), add:

```python
@dataclass(slots=True, frozen=True)
class ShortageProjection:
    below_threshold: bool
    deficit: int
    days_to_depletion: float | None
    days_to_threshold: float | None


def project_shortage(on_hand: int, min_stock: int, avg_daily: float) -> ShortageProjection:
    """Pure shortage math. ``avg_daily`` is average daily consumption (issues).

    - below_threshold: a positive threshold is set and on-hand is under it.
    - deficit: units to reorder back up to the threshold.
    - days_to_depletion: on_hand / avg_daily (None when there is no consumption).
    - days_to_threshold: days until on-hand reaches the threshold (0 if already
      at/below it; None when there is no consumption).
    """
    below_threshold = min_stock > 0 and on_hand < min_stock
    deficit = max(0, min_stock - on_hand)
    if avg_daily > 0:
        days_to_depletion: float | None = on_hand / avg_daily
        days_to_threshold: float | None = max(0, on_hand - min_stock) / avg_daily
    else:
        days_to_depletion = None
        days_to_threshold = None
    return ShortageProjection(
        below_threshold=below_threshold,
        deficit=deficit,
        days_to_depletion=days_to_depletion,
        days_to_threshold=days_to_threshold,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/unit/test_ppe_shortage_projection.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/stock.py tests/unit/test_ppe_shortage_projection.py
git commit -m "feat(p10-06): pure project_shortage forecast function"
```

---

## Task 3: Aggregation service `compute_shortages`

**Files:**
- Modify: `backend/app/modules/ppe/stock.py` (add at end of file)
- Test: `tests/api/test_ppe_shortage_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ppe_shortage_service.py
"""compute_shortages aggregation over batches + issue movements (P10-06)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.ppe import PPEItem, PPEStockBatch, PPEStockMovement
from app.modules.ppe.stock import KIND_ISSUE, KIND_RECEIPT, compute_shortages
from tests.utils.factories import TestDataFactory

NOW = datetime(2026, 7, 3, tzinfo=timezone.utc)


async def _mk_item(session, tenant_id, *, name, min_stock):
    item = PPEItem(tenant_id=tenant_id, name=name, min_stock=min_stock)
    session.add(item)
    await session.flush()
    return item


async def _mk_batch(session, tenant_id, item_id, qty):
    batch = PPEStockBatch(tenant_id=tenant_id, item_id=item_id, batch_no="B", quantity=qty)
    session.add(batch)
    await session.flush()
    return batch


async def _mk_issue(session, tenant_id, item_id, batch_id, qty, occurred_at):
    session.add(
        PPEStockMovement(
            tenant_id=tenant_id,
            item_id=item_id,
            batch_id=batch_id,
            kind=KIND_ISSUE,
            quantity_delta=-qty,
            occurred_at=occurred_at,
        )
    )
    await session.flush()


@pytest.mark.asyncio
async def test_only_items_with_threshold_are_watched(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await _mk_item(session, tenant.id, name="watched", min_stock=10)
        await _mk_item(session, tenant.id, name="ignored", min_stock=0)
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW)
    names = {r.item_name for r in rows}
    assert names == {"watched"}


@pytest.mark.asyncio
async def test_on_hand_sums_batches_and_flags_below(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _mk_item(session, tenant.id, name="caps", min_stock=20)
        await _mk_batch(session, tenant.id, item.id, 5)
        await _mk_batch(session, tenant.id, item.id, 4)
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW)
    assert len(rows) == 1
    assert rows[0].on_hand == 9
    assert rows[0].below_threshold is True
    assert rows[0].deficit == 11


@pytest.mark.asyncio
async def test_avg_daily_uses_only_issues_in_window(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _mk_item(session, tenant.id, name="gloves", min_stock=1)
        batch = await _mk_batch(session, tenant.id, item.id, 90)
        # 90 issued across the 90-day window => avg 1.0/day
        await _mk_issue(session, tenant.id, item.id, batch.id, 90, NOW - timedelta(days=10))
        # an issue OUTSIDE the window must be ignored
        await _mk_issue(session, tenant.id, item.id, batch.id, 999, NOW - timedelta(days=200))
        # a receipt must NOT count as consumption
        session.add(
            PPEStockMovement(
                tenant_id=tenant.id, item_id=item.id, batch_id=batch.id,
                kind=KIND_RECEIPT, quantity_delta=500, occurred_at=NOW - timedelta(days=5),
            )
        )
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW, window_days=90)
    assert rows[0].avg_daily_consumption == pytest.approx(1.0)
    assert rows[0].days_to_depletion == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_only_below_filters_out_healthy(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        low = await _mk_item(session, tenant.id, name="low", min_stock=10)
        await _mk_batch(session, tenant.id, low.id, 1)
        ok = await _mk_item(session, tenant.id, name="ok", min_stock=10)
        await _mk_batch(session, tenant.id, ok.id, 50)
        await session.commit()
    async with sessionmaker() as session:
        rows = await compute_shortages(session, tenant.id, now=NOW, only_below=True)
    assert [r.item_name for r in rows] == ["low"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_ppe_shortage_service.py -q`
Expected: FAIL with `ImportError: cannot import name 'compute_shortages'`.

- [ ] **Step 3: Implement the service**

In `backend/app/modules/ppe/stock.py`, append (imports at top already include `select`, `AsyncSession`; add `from datetime import date, timedelta` alongside the existing datetime import, and `from app.models.ppe import PPEItem` — verify PPEItem is importable from there):

```python
from datetime import date, timedelta  # add to the existing datetime import line
from app.models.ppe import PPEItem     # add near the PPEStockBatch import


@dataclass(slots=True, frozen=True)
class ShortageRow:
    item_id: str
    item_name: str
    min_stock: int
    on_hand: int
    deficit: int
    below_threshold: bool
    avg_daily_consumption: float
    days_to_depletion: float | None
    projected_breach_date: date | None


async def compute_shortages(
    session: AsyncSession,
    tenant_id: str,
    *,
    now: datetime,
    window_days: int = 90,
    only_below: bool = False,
) -> list[ShortageRow]:
    """Shortage report over items with a positive ``min_stock`` threshold.

    ``on_hand`` = Σ batch.quantity; ``avg_daily`` = Σ issued units in the
    trailing ``window_days`` / ``window_days``. ``now`` is injected for
    deterministic tests. Rows are sorted below-threshold-first, then by
    days-to-depletion ascending (unknown last).
    """
    items = list(
        (
            await session.execute(
                select(PPEItem).where(
                    PPEItem.tenant_id == tenant_id,
                    PPEItem.deleted_at.is_(None),
                    PPEItem.min_stock > 0,
                )
            )
        ).scalars().all()
    )
    if not items:
        return []
    item_ids = [i.id for i in items]

    on_hand_rows = (
        await session.execute(
            select(
                PPEStockBatch.item_id,
                func.coalesce(func.sum(PPEStockBatch.quantity), 0),
            )
            .where(
                PPEStockBatch.tenant_id == tenant_id,
                PPEStockBatch.item_id.in_(item_ids),
                PPEStockBatch.deleted_at.is_(None),
            )
            .group_by(PPEStockBatch.item_id)
        )
    ).all()
    on_hand = {iid: int(qty or 0) for iid, qty in on_hand_rows}

    cutoff = now - timedelta(days=window_days)
    consumed_rows = (
        await session.execute(
            select(
                PPEStockMovement.item_id,
                func.coalesce(func.sum(-PPEStockMovement.quantity_delta), 0),
            )
            .where(
                PPEStockMovement.tenant_id == tenant_id,
                PPEStockMovement.item_id.in_(item_ids),
                PPEStockMovement.kind == KIND_ISSUE,
                PPEStockMovement.occurred_at >= cutoff,
            )
            .group_by(PPEStockMovement.item_id)
        )
    ).all()
    consumed = {iid: int(total or 0) for iid, total in consumed_rows}

    rows: list[ShortageRow] = []
    for item in items:
        oh = on_hand.get(item.id, 0)
        avg_daily = consumed.get(item.id, 0) / window_days
        proj = project_shortage(oh, item.min_stock, avg_daily)
        if only_below and not proj.below_threshold:
            continue
        breach: date | None = None
        if proj.days_to_threshold is not None:
            breach = (now + timedelta(days=proj.days_to_threshold)).date()
        rows.append(
            ShortageRow(
                item_id=item.id,
                item_name=item.name,
                min_stock=item.min_stock,
                on_hand=oh,
                deficit=proj.deficit,
                below_threshold=proj.below_threshold,
                avg_daily_consumption=avg_daily,
                days_to_depletion=proj.days_to_depletion,
                projected_breach_date=breach,
            )
        )

    rows.sort(
        key=lambda r: (
            not r.below_threshold,
            r.days_to_depletion if r.days_to_depletion is not None else float("inf"),
        )
    )
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_ppe_shortage_service.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/stock.py tests/api/test_ppe_shortage_service.py
git commit -m "feat(p10-06): compute_shortages aggregation service"
```

---

## Task 4: `min_stock` in PPEItem schemas + create_item wiring

**Files:**
- Modify: `backend/app/schemas/ppe.py:14-55` (PPEItemCreate/Update/Read)
- Modify: `backend/app/api/routes/ppe.py:200-208` (create_item constructor)
- Test: `tests/api/test_ppe_shortage_api.py` (item-threshold portion)

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ppe_shortage_api.py
"""min_stock threshold + /ppe/stock/shortages endpoint (P10-06)."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _seed_item(client, headers, *, name="Каска", min_stock=0):
    resp = await client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value, "min_stock": min_stock},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()


async def _seed_batch(client, headers, item_id, *, no="B-1", qty=1):
    resp = await client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": no, "quantity": qty},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_item_create_and_patch_min_stock(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await _seed_item(async_client, headers, min_stock=7)
    assert created["min_stock"] == 7

    patched = await async_client.patch(
        f"/api/v1/ppe/items/{created['id']}",
        json={"min_stock": 15},
        headers=headers,
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["min_stock"] == 15
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_ppe_shortage_api.py::test_item_create_and_patch_min_stock -q`
Expected: FAIL (create response has no `min_stock`, or it stays 0 — `create_item` ignores it).

- [ ] **Step 3: Extend the schemas**

In `backend/app/schemas/ppe.py`:
- `PPEItemCreate`: add `min_stock: int = Field(default=0, ge=0)`
- `PPEItemUpdate`: add `min_stock: int | None = Field(default=None, ge=0)`
- `PPEItemRead`: add `min_stock: int`

- [ ] **Step 4: Wire `min_stock` into create_item**

In `backend/app/api/routes/ppe.py`, in `create_item` (line ~200), add `min_stock=payload.min_stock,` to the `PPEItem(...)` constructor. (`update_item` already flows via `payload.model_dump(exclude_unset=True)` + `setattr`; `_item_schema` uses `PPEItemRead.model_validate(item)` so the read field flows automatically.)

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/api/test_ppe_shortage_api.py::test_item_create_and_patch_min_stock -q`
Expected: PASS.

- [ ] **Step 6: Run the existing PPE item suite (regression — new required-read field must not break reads)**

Run: `python -m pytest tests/api/test_ppe_api.py -q`
Expected: PASS (existing items created without `min_stock` default to 0 and still serialize).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/api/test_ppe_shortage_api.py
git commit -m "feat(p10-06): min_stock in PPEItem schemas + create_item wiring"
```

---

## Task 5: `GET /ppe/stock/shortages` endpoint + shortage schemas

**Files:**
- Modify: `backend/app/schemas/ppe.py` (after `PPEStockLevelPage`, ~line 250)
- Modify: `backend/app/api/routes/ppe.py` (after `list_stock_levels`, ~line 1008)
- Test: `tests/api/test_ppe_shortage_api.py` (endpoint portion)

- [ ] **Step 1: Write the failing test (append to the Task 4 test file)**

```python
@pytest.mark.asyncio
async def test_shortages_lists_below_threshold_item(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        # warehouse flag ON for this tenant
        await data_factory.enable_feature(session=session, tenant_id=tenant.id, code="warehouse")
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item = await _seed_item(async_client, headers, name="Каска", min_stock=10)
    await _seed_batch(async_client, headers, item["id"], qty=3)

    resp = await async_client.get("/api/v1/ppe/stock/shortages", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["window_days"] == 90
    row = next(r for r in body["items"] if r["item_id"] == item["id"])
    assert row["min_stock"] == 10
    assert row["on_hand"] == 3
    assert row["deficit"] == 7
    assert row["below_threshold"] is True


@pytest.mark.asyncio
async def test_shortages_window_days_clamped(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await data_factory.enable_feature(session=session, tenant_id=tenant.id, code="warehouse")
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/shortages?window_days=0", headers=headers)
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_shortages_gated_by_warehouse_flag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)  # flag OFF (default)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/shortages", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
```

> Note: confirm the exact feature-enable + flag-off status code by reading `tests/api/test_ppe_warehouse_api.py` (it already exercises `WarehouseFeatureGate`). If the helper is named differently than `data_factory.enable_feature` or the gated status is not 404, mirror that file's helper/asserts exactly — do NOT invent a helper.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_ppe_shortage_api.py -k shortages -q`
Expected: FAIL (404 for an unknown route / no `/stock/shortages`).

- [ ] **Step 3: Add the shortage schemas**

In `backend/app/schemas/ppe.py`, after `PPEStockLevelPage` (line ~250), add (`from datetime import date` is already imported at top):

```python
class PPEStockShortageRead(BaseSchema):
    item_id: str
    item_name: str
    min_stock: int
    on_hand: int
    deficit: int
    below_threshold: bool
    avg_daily_consumption: float
    days_to_depletion: float | None
    projected_breach_date: date | None


class PPEStockShortagePage(BaseSchema):
    items: list[PPEStockShortageRead]
    total: int
    window_days: int
```

- [ ] **Step 4: Add the endpoint**

In `backend/app/api/routes/ppe.py`, after `list_stock_levels` (line ~1008), add (import `compute_shortages` from `app.modules.ppe.stock` at the top alongside the existing `record_movement` / `deplete_for_issue` imports; import `datetime, timezone` if not present):

```python
@router.get(
    "/stock/shortages",
    response_model=PPEStockShortagePage,
    dependencies=[WarehouseFeatureGate],
)
async def list_stock_shortages(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    window_days: int = Query(90, ge=1, le=365),
    only_below: bool = Query(False),
) -> PPEStockShortagePage:
    TenantContextValidator.ensure_tenant_context(tenant)
    rows = await compute_shortages(
        session,
        tenant.id,
        now=datetime.now(tz=timezone.utc),
        window_days=window_days,
        only_below=only_below,
    )
    items = [
        PPEStockShortageRead(
            item_id=r.item_id,
            item_name=r.item_name,
            min_stock=r.min_stock,
            on_hand=r.on_hand,
            deficit=r.deficit,
            below_threshold=r.below_threshold,
            avg_daily_consumption=r.avg_daily_consumption,
            days_to_depletion=r.days_to_depletion,
            projected_breach_date=r.projected_breach_date,
        )
        for r in rows
    ]
    return PPEStockShortagePage(items=items, total=len(items), window_days=window_days)
```

Add `PPEStockShortagePage`, `PPEStockShortageRead` to the schema import block at the top of `ppe.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/api/test_ppe_shortage_api.py -q`
Expected: PASS (all cases). If the flag-helper note in Step 1 required a fix, re-run.

- [ ] **Step 6: Run the warehouse regression sweep**

Run: `python -m pytest tests/api/test_ppe_warehouse_api.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_api.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/api/test_ppe_shortage_api.py
git commit -m "feat(p10-06): GET /ppe/stock/shortages min-stock + forecast endpoint"
```

---

## Task 6: Frontend — shortage section + min_stock in item form

**Files:**
- Modify: `frontend/src/api/warehouse.ts` (add DTO + `listShortages`)
- Modify: `frontend/src/pages/warehouse/WarehousePage.tsx` (add shortage section)
- Test: `frontend/src/__tests__/WarehousePage.test.tsx` (add cases + extend the mock)

- [ ] **Step 1: Write the failing test (extend the existing mock + add a case)**

In `frontend/src/__tests__/WarehousePage.test.tsx`, add `listShortages` to the mock object and its reset, and add:

```typescript
const listShortagesMock = vi.fn();
// inside vi.mock("@/api/warehouse", ...) warehouseApi object add:
//   listShortages: (...args: unknown[]) => listShortagesMock(...args)
// inside beforeEach add:
//   listShortagesMock.mockReset();
//   listShortagesMock.mockResolvedValue([]);

it("renders the shortage section with a below-threshold row", async () => {
  listLevelsMock.mockResolvedValue([]);
  listBatchesMock.mockResolvedValue([]);
  listMovementsMock.mockResolvedValue([]);
  listShortagesMock.mockResolvedValue([
    {
      item_id: "i1", item_name: "Каска", min_stock: 10, on_hand: 3, deficit: 7,
      below_threshold: true, avg_daily_consumption: 1, days_to_depletion: 3,
      projected_breach_date: "2026-07-06"
    }
  ]);

  render(<MemoryRouter><WarehousePage /></MemoryRouter>);
  await waitFor(() => expect(screen.getByText("Дефицит / мин-остаток")).toBeInTheDocument());
  expect(screen.getByText("Каска")).toBeInTheDocument();
  expect(screen.getByText("7")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --prefix frontend run test -- WarehousePage.test.tsx`
Expected: FAIL (`listShortages` not a function / "Дефицит / мин-остаток" not found).

- [ ] **Step 3: Add the DTO + client method**

In `frontend/src/api/warehouse.ts` add:

```typescript
export type PPEStockShortageDto = {
  item_id: string;
  item_name: string;
  min_stock: number;
  on_hand: number;
  deficit: number;
  below_threshold: boolean;
  avg_daily_consumption: number;
  days_to_depletion: number | null;
  projected_breach_date: string | null;
};

type ShortagePageResponse = { items: PPEStockShortageDto[]; total: number; window_days: number };
```

and inside `warehouseApi` add:

```typescript
  async listShortages(params?: { window_days?: number; only_below?: boolean }): Promise<PPEStockShortageDto[]> {
    const response = await apiClient.get<ShortagePageResponse>("/ppe/stock/shortages", { params });
    return response.data.items ?? [];
  }
```

- [ ] **Step 4: Add the shortage section to WarehousePage**

In `frontend/src/pages/warehouse/WarehousePage.tsx`:
- import the DTO type; add `const [shortages, setShortages] = useState<PPEStockShortageDto[]>([]);`
- in the load effect's `Promise.all`, add `warehouseApi.listShortages()` and `setShortages(...)`.
- render a `<Card>` titled "Дефицит / мин-остаток" with a `<Table>`: columns Позиция / Остаток / Порог / Дефицит / Дней до исчерпания / Дата пробоя. Row severity badge: red `<Badge variant="destructive">` when `below_threshold`, amber otherwise. Show `days_to_depletion ?? "—"` and `projected_breach_date ? formatDate(...) : "—"`. Header shows the count of `below_threshold` rows.

- [ ] **Step 5: Run test to verify it passes**

Run: `npm --prefix frontend run test -- WarehousePage.test.tsx`
Expected: PASS (existing cases + the new one).

- [ ] **Step 6: Typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: clean (0 errors).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/warehouse.ts frontend/src/pages/warehouse/WarehousePage.tsx frontend/src/__tests__/WarehousePage.test.tsx
git commit -m "feat(p10-06): warehouse shortage section (min-stock + forecast)"
```

---

## Task 7: Docs — roadmap, CHANGELOG, OpenAPI resnap, handoff

**Files:**
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` (P10-06 row)
- Modify: `CHANGELOG.md` (if present, top/unreleased)
- Modify: `AI_IMPLEMENTATION_REPORT.md` (handoff block)
- Modify: OpenAPI snapshot under `docs/stabilization/` (if the repo pins one — grep first)

- [ ] **Step 1: Update the roadmap P10-06 row**

In `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, extend the P10-06 evidence cell: add "мин-остаток `PPEItem.min_stock` (migration wa05) + прогноз дефицита `GET /ppe/stock/shortages` (скорость расхода по issue-движениям → дни до исчерпания/дата пробоя) + фронт-секция «Дефицит / мин-остаток»." Move "мин-остаток/прогноз дефицита" out of the "Остаётся" list (leave перемещения/поставщики/инвентаризация/мобильная выдача).

- [ ] **Step 2: CHANGELOG (only if `CHANGELOG.md` exists at repo root)**

```
- P10-06 СИЗ склад: per-item min-stock threshold (`ppeitem.min_stock`, migration wa05) + shortage forecast endpoint `GET /ppe/stock/shortages` (velocity from issue movements → days-to-depletion + projected breach date) + WarehousePage shortage section.
```

- [ ] **Step 3: OpenAPI resnap (only if a snapshot is pinned)**

Run: `grep -rl "stock/movements" docs/stabilization/ 2>/dev/null` — if a snapshot file lists PPE stock routes, regenerate it the same way the wa04 snapshot was produced (see the P10-06 stock-movements plan Task 10 for the exact command), so `/stock/shortages` is included. If no snapshot pins these routes, skip.

- [ ] **Step 4: Handoff note**

Append a session block to `AI_IMPLEMENTATION_REPORT.md` describing: model column wa05, `project_shortage` + `compute_shortages`, the endpoint, the frontend section, and the Next Step (P10-06 инвентаризация or поставщики).

- [ ] **Step 5: Full P10-06 regression sweep**

Run: `python -m pytest tests/unit/test_ppe_shortage_projection.py tests/api/test_ppe_shortage_service.py tests/api/test_ppe_shortage_api.py backend/tests/test_wa05_ppeitem_min_stock_migration.py tests/api/test_ppe_warehouse_api.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_api.py -q`
Expected: all PASS (judge by exit code — PowerShell may drop the summary line).

- [ ] **Step 6: Commit**

```bash
git add docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md AI_IMPLEMENTATION_REPORT.md CHANGELOG.md
git commit -m "docs(p10-06): roadmap + CHANGELOG + handoff for min-stock shortage forecast"
```

---

## Self-Review

**1. Spec coverage:**
- Model `PPEItem.min_stock` + migration wa05 → Task 1. ✅
- Watchlist `min_stock > 0` → Task 3 (`compute_shortages` filter) + Task 3 test. ✅
- Pure forecast (below/deficit/days) → Task 2. ✅
- avg_daily = only `kind=issue` in window → Task 3 (`KIND_ISSUE` + cutoff filter) + `test_avg_daily_uses_only_issues_in_window`. ✅
- Endpoint `GET /stock/shortages` behind `warehouse` flag, `ManagerAccess`, `window_days` clamp, `only_below`, **no ETag** (mirrors /stock/levels) → Task 5. ✅
- Threshold set via item CRUD → Task 4. ✅
- Frontend section + min_stock in item form → Task 6. ✅
- Edge cases (min_stock=0, avg=0, on_hand=0, flag off, window clamp) → Tasks 2/3/5 tests. ✅
- Out-of-scope (Command Center, notifications, suppliers/transfers/stocktake) → not planned (correct). ✅

**2. Placeholder scan:** No TBD/TODO. Two explicit "confirm against existing file, mirror exactly, do not invent" notes (feature-enable helper in Task 5 Step 1; OpenAPI snapshot in Task 7 Step 3) — these are guarded fallbacks with the exact file to read, because the helper name and snapshot presence are the only two facts not verifiable from the code already read. Primary code is complete.

**3. Type consistency:** `project_shortage(on_hand, min_stock, avg_daily) -> ShortageProjection(below_threshold, deficit, days_to_depletion, days_to_threshold)` (Task 2) is consumed unchanged in Task 3. `compute_shortages(session, tenant_id, *, now, window_days, only_below) -> list[ShortageRow]` (Task 3) matches the endpoint call (Task 5). DTO `PPEStockShortageRead` fields (Task 5) match `ShortageRow` fields (Task 3) match `PPEStockShortageDto` (Task 6). `min_stock` name identical across model/schema/frontend. `KIND_ISSUE` is the existing constant in `stock.py`. ✅
