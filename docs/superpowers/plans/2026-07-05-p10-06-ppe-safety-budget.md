# PPE Safety Budget (procurement plan vs actual) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a СИЗ safety-budget contour — a planned spend amount per period vs computed procurement actual (Σ receipt-qty × batch unit_cost), with a category breakdown.

**Architecture:** New `PPESafetyBudget` entity (period + planned amount, tenant-wide) + nullable `PPEStockBatch.unit_cost`. Actual is a **pure computed aggregate** over the append-only receipt movements (never persisted) — mirrors `compute_shortages`/`build_reorder_draft`. Additive migration `wa09`. Behind the `warehouse` feature flag. Honest-stock invariant untouched (cost is metadata; no new mutator).

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 (async) / Alembic; pytest (`tests/api/`); React/TS/Vite + vitest frontend.

**Spec:** `docs/superpowers/specs/2026-07-05-p10-06-ppe-safety-budget-design.md`
**Branch:** `feat/p10-06-ppe-safety-budget` (from `main`@`d4f1375c`; `wa09` chains from `wa08` in main).

---

## Conventions locked from the codebase (read before starting)

- **Models** are defined in `backend/app/models/ppe.py` and re-exported through TWO aggregators that callers import from: `backend/app/models/models.py` (import block + `__all__`) and `backend/app/models/ppe_registry.py` (import block + `__all__`). A new model class MUST be added to **all three** or imports fail.
- **Service** modules live in `backend/app/modules/ppe/` (see `suppliers.py` — the template for this slice's CRUD).
- **Routes** in `backend/app/api/routes/ppe.py`; warehouse endpoints use `dependencies=[WarehouseFeatureGate]`, `ManagerAccess` (read) / `EditorAccess` (write), `@audit_operation(...)`, and `compute_list_etag` for list ETag.
- **Schemas** in `backend/app/schemas/ppe.py` (base `BaseSchema`, pydantic v2). Money is `Numeric(14,2)` in DB, typed `float` in ORM & schemas (per `finance.py`/`tenant_billing.py`).
- **Tests** live in `tests/api/` (NOT `backend/tests/` — the DB fixtures `sessionmaker`/`data_factory` are in `tests/conftest.py`). DB service tests use `sessionmaker` + `data_factory.ensure_tenant(session=...)`; API tests use `async_client` + `make_auth_headers(RoleEnum.ADMIN)` and `_seed_item`/`_seed_batch` helpers. The `warehouse` flag is enabled by default in the test env (warehouse endpoints return 201/200 without explicit enabling).
- **Running backend tests (Windows worktree):** run via the **PowerShell tool** (Git-Bash segfaults on pytest), from repo root, using the global interpreter, ONE invocation with a long timeout (cold import ~2-3 min), batches of ≤4 files:
  `& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_ppe_budget_model.py -q`
  (pyproject sets `pythonpath=["backend","."]`, so no manual PYTHONPATH for pytest.)
- **Alembic does NOT run on SQLite** here (initial_schema JSONB); unit tests build the schema via `metadata.create_all`, so new columns/tables in the ORM are present in tests automatically. The migration is validated only by the **PG16 gate** (Task 7).
- **No manual PYTHONPATH for pytest**, but the OpenAPI snapshot script (Task 7) needs `$env:PYTHONPATH="backend"`.

## File structure

| File | Responsibility | Task |
|---|---|---|
| `backend/app/models/ppe.py` | `PPESafetyBudget` class + `PPEStockBatch.unit_cost` + `Numeric` import | 1 |
| `backend/app/models/models.py`, `.../ppe_registry.py` | re-export `PPESafetyBudget` (import + `__all__`) | 1 |
| `backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py` | additive migration | 1 |
| `backend/app/schemas/ppe.py` | budget schemas + `unit_cost` on batch schemas | 2 |
| `backend/app/modules/ppe/budget.py` | CRUD + `compute_budget_actual` | 3,4 |
| `backend/app/api/routes/ppe.py` | 5 budget routes + `unit_cost` in batch create | 5 |
| `frontend/src/api/warehouse.ts`, `pages/warehouse/WarehousePage.tsx` | budget section + batch `unit_cost` field | 6 |
| `frontend/src/__tests__/{WarehousePage,OpsPages}.test.tsx` | budget vitest + OpsPages mock fix | 6 |
| `tests/api/test_ppe_budget_*.py` | model/schema/service/actual/api tests | 1-5 |
| roadmap / CHANGELOG / handoff | docs | 7 |

---

## Task 1: Model + migration + re-exports

**Files:**
- Modify: `backend/app/models/ppe.py`
- Modify: `backend/app/models/models.py`
- Modify: `backend/app/models/ppe_registry.py`
- Create: `backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py`
- Test: `tests/api/test_ppe_budget_model.py`

- [ ] **Step 1: Write the failing model test**

`tests/api/test_ppe_budget_model.py`:

```python
"""ORM round-trip for PPESafetyBudget + PPEStockBatch.unit_cost (P10-06)."""
from __future__ import annotations

from datetime import date

import pytest

from app.models.models import PPEItem, PPESafetyBudget
from app.models.ppe_registry import PPEStockBatch
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_budget_roundtrip(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        b = PPESafetyBudget(
            tenant_id=tenant.id,
            name="Бюджет 2026",
            period_start=date(2026, 1, 1),
            period_end=date(2026, 12, 31),
            planned_amount=100000,
            notes="годовой",
        )
        session.add(b)
        await session.flush()
        await session.refresh(b)
        assert b.name == "Бюджет 2026"
        assert float(b.planned_amount) == 100000.0
        assert b.deleted_at is None


@pytest.mark.asyncio
async def test_batch_unit_cost_nullable(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        priced = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="B1", quantity=0, unit_cost=250
        )
        unpriced = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="B2", quantity=0
        )
        session.add_all([priced, unpriced])
        await session.flush()
        await session.refresh(priced)
        await session.refresh(unpriced)
        assert float(priced.unit_cost) == 250.0
        assert unpriced.unit_cost is None
```

- [ ] **Step 2: Run it, expect ImportError (PPESafetyBudget not defined)**

Run: `& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_ppe_budget_model.py -q` (PowerShell tool, timeout 600000)
Expected: FAIL — `ImportError: cannot import name 'PPESafetyBudget'`.

- [ ] **Step 3: Add the model + column in `backend/app/models/ppe.py`**

(a) Add `Numeric` to the sqlalchemy import block (currently `from sqlalchemy import (JSON, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text,)`) — insert `Numeric,` (keep alphabetical-ish, e.g. after `JSON,`).

(b) Add this class immediately after `class PPESupplier(...)` (ends ~line 115):

```python
class PPESafetyBudget(TenantBaseModel, SoftDeleteMixin):
    """PPE safety budget (P10-06 §12.4, СИЗ scope). Planned spend for a date-range
    period; actual is computed from receipt movements × batch.unit_cost (never
    persisted). Tenant-wide; overlapping periods are allowed."""

    __tablename__ = "ppe_safety_budget"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    planned_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
```

(c) In `class PPEStockBatch(...)`, add after the `supplier_id` mapped_column (~line 174), before the `item`/`supplier` relationships:

```python
    unit_cost: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
```

- [ ] **Step 4: Re-export in both aggregators**

(a) `backend/app/models/models.py` — in the `from app.models.ppe import (` block (contains `PPEStockBatch`, `PPESupplier`), add `PPESafetyBudget,`. Then in the `__all__` list (near `"PPESupplier",`), add `"PPESafetyBudget",`.

(b) `backend/app/models/ppe_registry.py` — add `PPESafetyBudget,` to the `from app.models.models import (` block and `"PPESafetyBudget",` to `__all__`.

- [ ] **Step 5: Create the migration `backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py`**

```python
"""ppe safety budget table + batch unit_cost (P10-06 §12.4 СИЗ scope).

Additive: creates ppe_safety_budget + adds nullable unit_cost to ppe_stock_batch.
No data backfill, no enum. Chains off wa08.

Revision ID: 20260705_wa09_ppe_safety_budget
Revises: 20260704_wa08_ppe_supplier
Create Date: 2026-07-05 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260705_wa09_ppe_safety_budget"
down_revision = "20260704_wa08_ppe_supplier"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_safety_budget",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("planned_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_ppe_safety_budget_tenant_id"), "ppe_safety_budget", ["tenant_id"]
    )
    op.add_column("ppe_stock_batch", sa.Column("unit_cost", sa.Numeric(14, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("ppe_stock_batch", "unit_cost")
    op.drop_index(op.f("ix_ppe_safety_budget_tenant_id"), table_name="ppe_safety_budget")
    op.drop_table("ppe_safety_budget")
```

- [ ] **Step 6: Run the model test — expect PASS**

Run: `& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_ppe_budget_model.py -q`
Expected: PASS (2 tests). Also sanity-import the migration: `& "…python.exe" -c "import importlib.util, pathlib; importlib.util.spec_from_file_location('m', 'backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py')"` (should not error).

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/ppe.py backend/app/models/models.py backend/app/models/ppe_registry.py backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py tests/api/test_ppe_budget_model.py
git commit -m "feat(p10-06): PPESafetyBudget model + batch.unit_cost + wa09 migration"
```

---

## Task 2: Schemas

**Files:**
- Modify: `backend/app/schemas/ppe.py`
- Test: `tests/api/test_ppe_budget_schema.py`

- [ ] **Step 1: Write the failing schema test**

`tests/api/test_ppe_budget_schema.py`:

```python
"""Validation for PPE safety budget + batch unit_cost schemas (P10-06)."""
from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.ppe import PPESafetyBudgetCreate, PPEStockBatchCreate


def test_period_end_before_start_rejected():
    with pytest.raises(ValidationError):
        PPESafetyBudgetCreate(
            name="x", period_start=date(2026, 12, 31), period_end=date(2026, 1, 1), planned_amount=1
        )


def test_planned_amount_non_negative():
    with pytest.raises(ValidationError):
        PPESafetyBudgetCreate(
            name="x", period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), planned_amount=-1
        )


def test_valid_budget_ok():
    b = PPESafetyBudgetCreate(
        name="2026", period_start=date(2026, 1, 1), period_end=date(2026, 12, 31), planned_amount=5000
    )
    assert b.planned_amount == 5000


def test_batch_unit_cost_optional_and_non_negative():
    assert PPEStockBatchCreate(item_id="i", batch_no="B").unit_cost is None
    assert PPEStockBatchCreate(item_id="i", batch_no="B", unit_cost=100).unit_cost == 100
    with pytest.raises(ValidationError):
        PPEStockBatchCreate(item_id="i", batch_no="B", unit_cost=-5)
```

- [ ] **Step 2: Run it, expect FAIL (schemas/fields missing)**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_schema.py -q`
Expected: FAIL — `ImportError` for `PPESafetyBudgetCreate` (and later, `unit_cost` unknown).

- [ ] **Step 3: Add schemas in `backend/app/schemas/ppe.py`**

(a) Change the pydantic import (line 8) to add `model_validator`:
`from pydantic import Field, field_validator, model_validator`

(b) Add `unit_cost: float | None = Field(default=None, ge=0)` to `PPEStockBatchCreate` (after `supplier_id`), the same line to `PPEStockBatchUpdate` (after `supplier_id`), and `unit_cost: float | None` to `PPEStockBatchRead` (after `supplier_id`).

(c) Append this budget block after `class PPESupplierPage` (~line 95):

```python
class PPESafetyBudgetCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    period_start: date
    period_end: date
    planned_amount: float = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _check_period(self) -> "PPESafetyBudgetCreate":
        if self.period_end < self.period_start:
            raise ValueError("period_end must be >= period_start")
        return self


class PPESafetyBudgetUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    period_start: date | None = None
    period_end: date | None = None
    planned_amount: float | None = Field(default=None, ge=0)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _check_period(self) -> "PPESafetyBudgetUpdate":
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("period_end must be >= period_start")
        return self


class PPESafetyBudgetRead(BaseSchema):
    id: str
    name: str
    period_start: date
    period_end: date
    planned_amount: float
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PPESafetyBudgetPage(BaseSchema):
    items: list[PPESafetyBudgetRead]
    total: int


class PPEBudgetCategoryActualRead(BaseSchema):
    category: str
    amount: float


class PPESafetyBudgetDetail(PPESafetyBudgetRead):
    actual_total: float
    remaining: float
    by_category: list[PPEBudgetCategoryActualRead]
    priced_receipt_count: int
    unpriced_receipt_count: int
```

- [ ] **Step 4: Run it, expect PASS**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_schema.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/ppe.py tests/api/test_ppe_budget_schema.py
git commit -m "feat(p10-06): safety-budget schemas + batch unit_cost field"
```

---

## Task 3: Service CRUD (`budget.py`)

**Files:**
- Create: `backend/app/modules/ppe/budget.py`
- Test: `tests/api/test_ppe_budget_service.py`

- [ ] **Step 1: Write the failing service test**

`tests/api/test_ppe_budget_service.py`:

```python
"""DB-level CRUD for the PPE safety budget service (P10-06)."""
from __future__ import annotations

from datetime import date

import pytest

from app.modules.ppe.budget import (
    BudgetNotFound,
    create_budget,
    get_budget,
    list_budgets,
    soft_delete_budget,
    update_budget,
)
from tests.utils.factories import TestDataFactory

Y = dict(period_start=date(2026, 1, 1), period_end=date(2026, 12, 31))


@pytest.mark.asyncio
async def test_create_get(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        b = await create_budget(session, tenant_id=t.id, name="2026", planned_amount=1000, **Y)
        got = await get_budget(session, t.id, b.id)
        assert got.name == "2026"
        assert float(got.planned_amount) == 1000.0


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        a = await create_budget(session, tenant_id=t.id, name="A", planned_amount=1, **Y)
        await create_budget(session, tenant_id=t.id, name="B", planned_amount=1, **Y)
        await soft_delete_budget(session, t.id, a.id)
        items, total = await list_budgets(session, t.id, limit=50, offset=0)
        assert total == 1
        assert [x.name for x in items] == ["B"]


@pytest.mark.asyncio
async def test_update_allowlist_and_missing(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        b = await create_budget(session, tenant_id=t.id, name="Old", planned_amount=1, **Y)
        upd = await update_budget(session, t.id, b.id, name="New", planned_amount=2, bogus="x")
        assert upd.name == "New"
        assert float(upd.planned_amount) == 2.0
        assert not hasattr(upd, "bogus")
        with pytest.raises(BudgetNotFound):
            await get_budget(session, t.id, "nope")


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        b = await create_budget(session, tenant_id=t1.id, name="T1", planned_amount=1, **Y)
        with pytest.raises(BudgetNotFound):
            await get_budget(session, t2.id, b.id)
```

- [ ] **Step 2: Run it, expect FAIL (module missing)**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_service.py -q`
Expected: FAIL — `ModuleNotFoundError: app.modules.ppe.budget`.

- [ ] **Step 3: Create `backend/app/modules/ppe/budget.py` (CRUD only for now)**

```python
"""PPE safety budget service (P10-06 §12.4, СИЗ scope).

Thin CRUD over PPESafetyBudget (mirrors suppliers.py) plus compute_budget_actual
(added in the next task) which derives procurement actual from the movement ledger.
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ppe_registry import (
    PPEItem,
    PPESafetyBudget,
    PPEStockBatch,
    PPEStockMovement,
)

_UPDATABLE_FIELDS = frozenset({"name", "period_start", "period_end", "planned_amount", "notes"})


class BudgetNotFound(Exception):
    def __init__(self, budget_id: str) -> None:
        super().__init__(f"PPE safety budget not found: {budget_id}")
        self.budget_id = budget_id


async def _load_budget(session: AsyncSession, tenant_id: str, budget_id: str) -> PPESafetyBudget:
    stmt = select(PPESafetyBudget).where(
        PPESafetyBudget.id == budget_id,
        PPESafetyBudget.tenant_id == tenant_id,
        PPESafetyBudget.deleted_at.is_(None),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise BudgetNotFound(budget_id)
    return row


async def create_budget(
    session: AsyncSession,
    *,
    tenant_id: str,
    name: str,
    period_start: date,
    period_end: date,
    planned_amount: float = 0,
    notes: str | None = None,
) -> PPESafetyBudget:
    budget = PPESafetyBudget(
        tenant_id=tenant_id,
        name=name,
        period_start=period_start,
        period_end=period_end,
        planned_amount=planned_amount,
        notes=notes,
    )
    session.add(budget)
    await session.flush()
    await session.refresh(budget)
    return budget


async def get_budget(session: AsyncSession, tenant_id: str, budget_id: str) -> PPESafetyBudget:
    return await _load_budget(session, tenant_id, budget_id)


async def list_budgets(
    session: AsyncSession, tenant_id: str, *, limit: int, offset: int
) -> tuple[list[PPESafetyBudget], int]:
    base = (
        PPESafetyBudget.tenant_id == tenant_id,
        PPESafetyBudget.deleted_at.is_(None),
    )
    items = list(
        (
            await session.execute(
                select(PPESafetyBudget)
                .where(*base)
                .order_by(PPESafetyBudget.period_start.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    total = (await session.execute(select(func.count()).where(*base))).scalar_one()
    return items, int(total or 0)


async def update_budget(
    session: AsyncSession, tenant_id: str, budget_id: str, **fields
) -> PPESafetyBudget:
    """Update a budget; only keys in ``_UPDATABLE_FIELDS`` are applied."""
    budget = await _load_budget(session, tenant_id, budget_id)
    for key, value in fields.items():
        if key in _UPDATABLE_FIELDS:
            setattr(budget, key, value)
    await session.flush()
    await session.refresh(budget)
    return budget


async def soft_delete_budget(session: AsyncSession, tenant_id: str, budget_id: str) -> None:
    budget = await _load_budget(session, tenant_id, budget_id)
    budget.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()
```

(Note: `date`/`time`/`PPEItem`/`PPEStockBatch`/`PPEStockMovement` are imported now for use in Task 4; ruff may warn F401 until then — that's fine, Task 4 lands in the same slice. If you run ruff between tasks, Task 4 resolves it.)

- [ ] **Step 4: Run it, expect PASS**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_service.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/budget.py tests/api/test_ppe_budget_service.py
git commit -m "feat(p10-06): safety-budget CRUD service"
```

---

## Task 4: Service `compute_budget_actual`

**Files:**
- Modify: `backend/app/modules/ppe/budget.py`
- Test: `tests/api/test_ppe_budget_actual_service.py`

- [ ] **Step 1: Write the failing compute test**

`tests/api/test_ppe_budget_actual_service.py`:

```python
"""Procurement actual computation for the safety budget (P10-06)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.models import PPEItem, PPEItemCategory
from app.models.ppe_registry import PPEStockBatch, PPEStockMovement
from app.modules.ppe.budget import compute_budget_actual
from tests.utils.factories import TestDataFactory

PS, PE = date(2026, 1, 1), date(2026, 12, 31)


async def _item(session, tenant_id, *, name, category=PPEItemCategory.HEAD):
    it = PPEItem(tenant_id=tenant_id, name=name, category=category)
    session.add(it)
    await session.flush()
    return it


async def _batch(session, tenant_id, item_id, *, unit_cost, no="B"):
    b = PPEStockBatch(
        tenant_id=tenant_id, item_id=item_id, batch_no=no, quantity=0, unit_cost=unit_cost
    )
    session.add(b)
    await session.flush()
    return b


async def _movement(session, tenant_id, item_id, batch_id, *, kind, delta, when):
    m = PPEStockMovement(
        tenant_id=tenant_id,
        item_id=item_id,
        batch_id=batch_id,
        kind=kind,
        quantity_delta=delta,
        occurred_at=when,
    )
    session.add(m)
    await session.flush()
    return m


@pytest.mark.asyncio
async def test_sums_receipts_in_period(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        it = await _item(session, t.id, name="Каска")
        b = await _batch(session, t.id, it.id, unit_cost=100)
        # in period: 3 units * 100 = 300
        await _movement(session, t.id, it.id, b.id, kind="receipt", delta=3,
                        when=datetime(2026, 6, 1, tzinfo=timezone.utc))
        # out of period: ignored
        await _movement(session, t.id, it.id, b.id, kind="receipt", delta=5,
                        when=datetime(2025, 6, 1, tzinfo=timezone.utc))
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 300.0
        assert actual.priced_receipt_count == 1
        assert actual.unpriced_receipt_count == 0


@pytest.mark.asyncio
async def test_only_receipt_kind_counts(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        it = await _item(session, t.id, name="Каска")
        b = await _batch(session, t.id, it.id, unit_cost=100)
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        await _movement(session, t.id, it.id, b.id, kind="receipt", delta=2, when=when)
        for kind, delta in [("issue", -1), ("writeoff", -1), ("adjustment", 4), ("transfer", -1)]:
            await _movement(session, t.id, it.id, b.id, kind=kind, delta=delta, when=when)
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 200.0  # only the receipt of 2*100


@pytest.mark.asyncio
async def test_unpriced_excluded_but_counted(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        it = await _item(session, t.id, name="Каска")
        priced = await _batch(session, t.id, it.id, unit_cost=100, no="P")
        unpriced = await _batch(session, t.id, it.id, unit_cost=None, no="U")
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        await _movement(session, t.id, it.id, priced.id, kind="receipt", delta=2, when=when)
        await _movement(session, t.id, it.id, unpriced.id, kind="receipt", delta=9, when=when)
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 200.0
        assert actual.priced_receipt_count == 1
        assert actual.unpriced_receipt_count == 1


@pytest.mark.asyncio
async def test_category_breakdown(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t = await data_factory.ensure_tenant(session=session)
        head = await _item(session, t.id, name="Каска", category=PPEItemCategory.HEAD)
        hands = await _item(session, t.id, name="Перчатки", category=PPEItemCategory.HANDS)
        bh = await _batch(session, t.id, head.id, unit_cost=100, no="H")
        bg = await _batch(session, t.id, hands.id, unit_cost=10, no="G")
        when = datetime(2026, 6, 1, tzinfo=timezone.utc)
        await _movement(session, t.id, head.id, bh.id, kind="receipt", delta=1, when=when)  # 100
        await _movement(session, t.id, hands.id, bg.id, kind="receipt", delta=2, when=when)  # 20
        actual = await compute_budget_actual(session, t.id, PS, PE)
        assert actual.actual_total == 120.0
        cats = {c.category: c.amount for c in actual.by_category}
        assert cats == {"head": 100.0, "hands": 20.0}
        assert actual.by_category[0].category == "head"  # sorted by amount desc
```

- [ ] **Step 2: Run it, expect FAIL (compute_budget_actual missing)**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_actual_service.py -q`
Expected: FAIL — `ImportError: compute_budget_actual`.

- [ ] **Step 3: Add the dataclasses + function to `backend/app/modules/ppe/budget.py`**

Add near the top (after the imports, before `_UPDATABLE_FIELDS`):

```python
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class BudgetCategoryActual:
    category: str
    amount: float


@dataclass(slots=True, frozen=True)
class BudgetActual:
    actual_total: float
    by_category: list[BudgetCategoryActual]
    priced_receipt_count: int
    unpriced_receipt_count: int
```

Add this function at the end of the module:

```python
async def compute_budget_actual(
    session: AsyncSession, tenant_id: str, period_start: date, period_end: date
) -> BudgetActual:
    """Procurement actual = Σ(receipt quantity × batch.unit_cost) within the period.

    Only ``kind='receipt'`` positive movements count (issue/writeoff/adjustment/
    transfer are not procurement). Receipts on batches without a ``unit_cost`` are
    excluded from the total but counted in ``unpriced_receipt_count`` so callers can
    warn that the figure is incomplete. Single join query — no N+1. The ledger is the
    source of truth for spend, so a later soft-delete of the batch does not un-spend it.
    """
    start_dt = datetime.combine(period_start, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(period_end, time.max, tzinfo=timezone.utc)
    stmt = (
        select(PPEItem.category, PPEStockMovement.quantity_delta, PPEStockBatch.unit_cost)
        .join(PPEStockBatch, PPEStockMovement.batch_id == PPEStockBatch.id)
        .join(PPEItem, PPEStockMovement.item_id == PPEItem.id)
        .where(
            PPEStockMovement.tenant_id == tenant_id,
            PPEStockMovement.kind == "receipt",
            PPEStockMovement.quantity_delta > 0,
            PPEStockMovement.occurred_at >= start_dt,
            PPEStockMovement.occurred_at <= end_dt,
        )
    )
    rows = (await session.execute(stmt)).all()

    total = 0.0
    priced = 0
    unpriced = 0
    by_cat: dict[str, float] = {}
    for category, delta, unit_cost in rows:
        if unit_cost is None:
            unpriced += 1
            continue
        priced += 1
        amount = float(unit_cost) * int(delta)
        total += amount
        key = category.value if hasattr(category, "value") else (category or "—")
        by_cat[key] = by_cat.get(key, 0.0) + amount

    by_category = [
        BudgetCategoryActual(category=k, amount=v)
        for k, v in sorted(by_cat.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return BudgetActual(
        actual_total=total,
        by_category=by_category,
        priced_receipt_count=priced,
        unpriced_receipt_count=unpriced,
    )
```

- [ ] **Step 4: Run it, expect PASS**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_actual_service.py -q`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/budget.py tests/api/test_ppe_budget_actual_service.py
git commit -m "feat(p10-06): compute_budget_actual (procurement, category breakdown)"
```

---

## Task 5: Routes (CRUD + detail + batch unit_cost)

**Files:**
- Modify: `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_budget_api.py`

- [ ] **Step 1: Write the failing API test**

`tests/api/test_ppe_budget_api.py`:

```python
"""API contract for PPE safety budget (P10-06)."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory

WIDE = {"name": "Всё время", "period_start": "2000-01-01", "period_end": "2100-01-01",
        "planned_amount": 10000}


async def _seed_item(async_client, headers, *, name="Каска"):
    resp = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": name, "category": PPEItemCategory.HEAD.value},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()["id"]


@pytest.mark.asyncio
async def test_budget_crud_and_actual(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    # create budget
    resp = await async_client.post("/api/v1/ppe/budgets", json=WIDE, headers=headers)
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    budget_id = resp.json()["id"]

    # list
    lst = await async_client.get("/api/v1/ppe/budgets", headers=headers)
    assert lst.status_code == status.HTTP_200_OK
    assert lst.json()["total"] == 1

    # seed a priced receipt (batch create with unit_cost + quantity → receipt movement now())
    item_id = await _seed_item(async_client, headers)
    batch = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B1", "quantity": 4, "unit_cost": 250},
        headers=headers,
    )
    assert batch.status_code == status.HTTP_201_CREATED, batch.text
    assert batch.json()["unit_cost"] == 250

    # detail → actual = 4 * 250 = 1000, remaining = 9000
    detail = await async_client.get(f"/api/v1/ppe/budgets/{budget_id}", headers=headers)
    assert detail.status_code == status.HTTP_200_OK, detail.text
    body = detail.json()
    assert body["actual_total"] == 1000.0
    assert body["remaining"] == 9000.0
    assert body["priced_receipt_count"] == 1
    assert body["by_category"][0]["category"] == "head"

    # patch
    patched = await async_client.patch(
        f"/api/v1/ppe/budgets/{budget_id}", json={"planned_amount": 20000}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["planned_amount"] == 20000

    # delete
    dele = await async_client.delete(f"/api/v1/ppe/budgets/{budget_id}", headers=headers)
    assert dele.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"/api/v1/ppe/budgets/{budget_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_period_order_422(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/ppe/budgets",
        json={"name": "bad", "period_start": "2026-12-31", "period_end": "2026-01-01",
              "planned_amount": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text
```

- [ ] **Step 2: Run it, expect FAIL (routes missing → 404/405)**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_api.py -q`
Expected: FAIL — POST `/ppe/budgets` returns 404 (no route yet).

- [ ] **Step 3: Wire batch `unit_cost` + add budget routes in `backend/app/api/routes/ppe.py`**

(a) Imports — add to the `from app.modules.ppe.suppliers import (...)` area a new import block:

```python
from app.modules.ppe.budget import (
    BudgetNotFound,
    compute_budget_actual,
    create_budget,
    get_budget,
    list_budgets,
    soft_delete_budget,
    update_budget,
)
```

And add the budget schemas to the `from app.schemas.ppe import (...)` block (wherever PPE schemas are imported): `PPEBudgetCategoryActualRead`, `PPESafetyBudgetCreate`, `PPESafetyBudgetDetail`, `PPESafetyBudgetPage`, `PPESafetyBudgetRead`, `PPESafetyBudgetUpdate`. (If schemas are imported via `from app.schemas.ppe import *` or a long list, add these names to the list.)

(b) In `create_stock_batch` (the `PPEStockBatch(...)` constructor, ~line 1109), add `unit_cost=payload.unit_cost,` alongside `supplier_id=payload.supplier_id,`. (Update path already applies `unit_cost` generically via `setattr` over `model_dump(exclude_unset=True)`, and Read already includes it via schema — no change needed there.)

(c) Add the budget route section (place after the supplier routes block, i.e. after `delete_supplier_endpoint`, ~line 1022):

```python
# --- PPE safety budget (P10-06 §12.4, СИЗ scope) ----------------------------


@router.post(
    "/budgets",
    response_model=PPESafetyBudgetRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("create", "ppe_safety_budget")
async def create_budget_endpoint(
    payload: PPESafetyBudgetCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPESafetyBudgetRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    budget = await create_budget(
        session,
        tenant_id=tenant.id,
        name=payload.name,
        period_start=payload.period_start,
        period_end=payload.period_end,
        planned_amount=payload.planned_amount,
        notes=payload.notes,
    )
    return PPESafetyBudgetRead.model_validate(budget)


@router.get(
    "/budgets",
    response_model=PPESafetyBudgetPage,
    dependencies=[WarehouseFeatureGate],
)
async def list_budgets_endpoint(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPESafetyBudgetPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    items, total = await list_budgets(session, tenant.id, limit=limit, offset=offset)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[("total", total), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PPESafetyBudgetPage(
        items=[PPESafetyBudgetRead.model_validate(b) for b in items], total=total
    )


@router.get(
    "/budgets/{budget_id}",
    response_model=PPESafetyBudgetDetail,
    dependencies=[WarehouseFeatureGate],
)
async def get_budget_endpoint(
    budget_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
) -> PPESafetyBudgetDetail:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        budget = await get_budget(session, tenant.id, budget_id)
    except BudgetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE safety budget not found") from exc
    actual = await compute_budget_actual(session, tenant.id, budget.period_start, budget.period_end)
    base = PPESafetyBudgetRead.model_validate(budget)
    return PPESafetyBudgetDetail(
        **base.model_dump(),
        actual_total=actual.actual_total,
        remaining=float(base.planned_amount) - actual.actual_total,
        by_category=[
            PPEBudgetCategoryActualRead(category=c.category, amount=c.amount)
            for c in actual.by_category
        ],
        priced_receipt_count=actual.priced_receipt_count,
        unpriced_receipt_count=actual.unpriced_receipt_count,
    )


@router.patch(
    "/budgets/{budget_id}",
    response_model=PPESafetyBudgetRead,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("update", "ppe_safety_budget")
async def update_budget_endpoint(
    budget_id: str,
    payload: PPESafetyBudgetUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PPESafetyBudgetRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        budget = await update_budget(
            session, tenant.id, budget_id, **payload.model_dump(exclude_unset=True)
        )
    except BudgetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE safety budget not found") from exc
    return PPESafetyBudgetRead.model_validate(budget)


@router.delete(
    "/budgets/{budget_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[WarehouseFeatureGate],
)
@audit_operation("delete", "ppe_safety_budget")
async def delete_budget_endpoint(
    budget_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await soft_delete_budget(session, tenant.id, budget_id)
    except BudgetNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE safety budget not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

- [ ] **Step 4: Run the API test — expect PASS**

Run: `& "…python.exe" -m pytest tests/api/test_ppe_budget_api.py -q`
Expected: PASS (2 tests). If PATCH's period validator complains on single-field update, note the `PPESafetyBudgetUpdate` validator already guards `None` — should be fine.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/ppe.py tests/api/test_ppe_budget_api.py
git commit -m "feat(p10-06): safety-budget routes + batch unit_cost wiring"
```

---

## Task 6: Frontend (budget section + batch unit_cost + OpsPages fix)

**Files:**
- Modify: `frontend/src/api/warehouse.ts`
- Modify: `frontend/src/pages/warehouse/WarehousePage.tsx`
- Modify: `frontend/src/__tests__/OpsPages.test.tsx` (re-apply pre-existing warehouse-mock fix + `listBudgets`)
- Test: `frontend/src/__tests__/WarehousePage.test.tsx` (append budget cases)

Run frontend tests via Bash: `cd "…/frontend" && npx vitest run src/__tests__/WarehousePage.test.tsx` ; types `npx tsc --noEmit`.

- [ ] **Step 1: Add the API client (`frontend/src/api/warehouse.ts`)**

Add `unit_cost?: number | null;` to `StockBatchDto` (after `supplier_id`). Add DTOs + methods (place near the supplier methods):

```ts
export type BudgetDto = {
  id: string;
  name: string;
  period_start: string;
  period_end: string;
  planned_amount: number;
  notes?: string | null;
  created_at: string;
  updated_at: string;
};

export type BudgetCategoryActualDto = { category: string; amount: number };

export type BudgetDetailDto = BudgetDto & {
  actual_total: number;
  remaining: number;
  by_category: BudgetCategoryActualDto[];
  priced_receipt_count: number;
  unpriced_receipt_count: number;
};

export type BudgetCreateInput = {
  name: string;
  period_start: string;
  period_end: string;
  planned_amount: number;
  notes?: string | null;
};
```

Add methods to the `warehouseApi` object:

```ts
  async listBudgets(): Promise<BudgetDto[]> {
    const res = await apiClient.get<{ items: BudgetDto[]; total: number }>("/ppe/budgets", {
      params: { limit: 100, offset: 0 }
    });
    return res.data.items ?? [];
  },
  async getBudget(id: string): Promise<BudgetDetailDto> {
    const res = await apiClient.get<BudgetDetailDto>(`/ppe/budgets/${id}`);
    return res.data;
  },
  async createBudget(input: BudgetCreateInput): Promise<BudgetDto> {
    const res = await apiClient.post<BudgetDto>("/ppe/budgets", input);
    return res.data;
  },
  async updateBudget(id: string, input: Partial<BudgetCreateInput>): Promise<BudgetDto> {
    const res = await apiClient.patch<BudgetDto>(`/ppe/budgets/${id}`, input);
    return res.data;
  },
  async deleteBudget(id: string): Promise<void> {
    await apiClient.delete(`/ppe/budgets/${id}`);
  },
```

(Match the exact method style already used by the supplier methods in this file — e.g. whether they return `.data.items` or a page object. Read the existing `listSuppliers`/`getReorderDraft` methods and mirror them precisely.)

- [ ] **Step 2: Add the WarehousePage budget section**

In `frontend/src/pages/warehouse/WarehousePage.tsx`, follow the existing **«Поставщики»** section as the template (state, load-on-mount via `warehouseApi.listBudgets`, a create/edit form, a list, error banner). Requirements — use these exact Russian strings so the test can assert them:
- Section heading: `Бюджет безопасности`.
- Create form fields: `Название` (text), `Начало периода` / `Конец периода` (date inputs), `Плановая сумма` (number), optional `Заметки`; submit button `Создать бюджет`.
- List rows show: name, period (`period_start – period_end`), `План: {planned_amount}`.
- Clicking a budget row/button `Открыть` loads `warehouseApi.getBudget(id)` and shows detail: `Факт: {actual_total}`, `Остаток: {remaining}`, a category breakdown list (`{category}: {amount}`), and — when `unpriced_receipt_count > 0` — a warning line `Приходов без цены: {n}`.
- Also add a `Цена за единицу` number input to the existing **«Новая партия (приёмка)»** batch form, sending `unit_cost` in the create-batch payload.
- Add `listBudgets`/`getBudget`/`createBudget`/`updateBudget`/`deleteBudget` to `warehouseApi` load calls as needed. Load budgets on mount alongside the other sections.

- [ ] **Step 3: Re-apply the OpsPages warehouse mock fix (pre-existing) + add `listBudgets`**

In `frontend/src/__tests__/OpsPages.test.tsx`, the `vi.mock("@/api/warehouse", ...)` block currently mocks only `listLevels`/`listBatches`. Replace it with the full set (WarehousePage now also loads budgets):

```tsx
const listMovementsMock = vi.fn();
const listShortagesMock = vi.fn();
const listCountsMock = vi.fn();
const listTransfersMock = vi.fn();
const listLevelsByLocationMock = vi.fn();
const listSuppliersMock = vi.fn();
const getReorderDraftMock = vi.fn();
const listBudgetsMock = vi.fn();

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: (...a: unknown[]) => listLevelsMock(...a),
    listBatches: (...a: unknown[]) => listBatchesMock(...a),
    listMovements: (...a: unknown[]) => listMovementsMock(...a),
    listShortages: (...a: unknown[]) => listShortagesMock(...a),
    listCounts: (...a: unknown[]) => listCountsMock(...a),
    listTransfers: (...a: unknown[]) => listTransfersMock(...a),
    listLevelsByLocation: (...a: unknown[]) => listLevelsByLocationMock(...a),
    listSuppliers: (...a: unknown[]) => listSuppliersMock(...a),
    getReorderDraft: (...a: unknown[]) => getReorderDraftMock(...a),
    listBudgets: (...a: unknown[]) => listBudgetsMock(...a)
  }
}));
```

And in `beforeEach`, add resets + empty-list defaults for the new mocks:

```tsx
    listMovementsMock.mockReset();
    listShortagesMock.mockReset();
    listCountsMock.mockReset();
    listTransfersMock.mockReset();
    listLevelsByLocationMock.mockReset();
    listSuppliersMock.mockReset();
    getReorderDraftMock.mockReset();
    listBudgetsMock.mockReset();
    listMovementsMock.mockResolvedValue([]);
    listShortagesMock.mockResolvedValue([]);
    listCountsMock.mockResolvedValue([]);
    listTransfersMock.mockResolvedValue([]);
    listLevelsByLocationMock.mockResolvedValue([]);
    listSuppliersMock.mockResolvedValue([]);
    getReorderDraftMock.mockResolvedValue({ groups: [], total_lines: 0, total_deficit: 0 });
    listBudgetsMock.mockResolvedValue([]);
```

(If the WarehousePage uses additional warehouse methods on mount that aren't listed here, mirror `WarehousePage.test.tsx`'s full mock — read it and match the complete set + `listBudgets`.)

- [ ] **Step 4: Append budget vitest cases to `frontend/src/__tests__/WarehousePage.test.tsx`**

Add a `listBudgetsMock`, `getBudgetMock`, `createBudgetMock` to the existing warehouse mock in that file (it already mocks the full `warehouseApi`; add these three), reset+default them in `beforeEach` (`listBudgetsMock.mockResolvedValue([])`), then add:

```tsx
  it("renders the safety budget section with a budget row", async () => {
    listBudgetsMock.mockResolvedValue([
      { id: "bud-1", name: "Бюджет 2026", period_start: "2026-01-01", period_end: "2026-12-31",
        planned_amount: 100000, notes: null, created_at: "2026-01-01", updated_at: "2026-01-01" }
    ]);
    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    expect(await screen.findByText("Бюджет безопасности")).toBeInTheDocument();
    expect(await screen.findByText("Бюджет 2026")).toBeInTheDocument();
  });

  it("shows computed actual + remaining + unpriced warning on open", async () => {
    listBudgetsMock.mockResolvedValue([
      { id: "bud-1", name: "Бюджет 2026", period_start: "2026-01-01", period_end: "2026-12-31",
        planned_amount: 100000, notes: null, created_at: "2026-01-01", updated_at: "2026-01-01" }
    ]);
    getBudgetMock.mockResolvedValue({
      id: "bud-1", name: "Бюджет 2026", period_start: "2026-01-01", period_end: "2026-12-31",
      planned_amount: 100000, notes: null, created_at: "2026-01-01", updated_at: "2026-01-01",
      actual_total: 30000, remaining: 70000,
      by_category: [{ category: "head", amount: 30000 }],
      priced_receipt_count: 2, unpriced_receipt_count: 1
    });
    render(<MemoryRouter><WarehousePage /></MemoryRouter>);
    fireEvent.click(await screen.findByRole("button", { name: /Открыть/ }));
    expect(await screen.findByText(/Приходов без цены: 1/)).toBeInTheDocument();
  });
```

(Adjust selectors to match the exact markup you wrote in Step 2; the assertions target the required strings from Step 2.)

- [ ] **Step 5: Run frontend gates**

Run (Bash from `frontend/`):
```
npx vitest run src/__tests__/WarehousePage.test.tsx src/__tests__/OpsPages.test.tsx
npx tsc --noEmit
```
Expected: both test files pass; tsc 0.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/warehouse.ts frontend/src/pages/warehouse/WarehousePage.tsx frontend/src/__tests__/WarehousePage.test.tsx frontend/src/__tests__/OpsPages.test.tsx
git commit -m "feat(p10-06): warehouse safety-budget UI + batch unit_cost field"
```

---

## Task 7: Docs + full gates

**Files:**
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, `CHANGELOG.md`, `AI_IMPLEMENTATION_REPORT.md`

- [ ] **Step 1: Backend regression (batched, PowerShell)**

Run the PPE budget + adjacent suites (batches ≤4 files), each one invocation, timeout 600000:
```
& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_ppe_budget_model.py tests/api/test_ppe_budget_schema.py tests/api/test_ppe_budget_service.py tests/api/test_ppe_budget_actual_service.py -q
& "C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe" -m pytest tests/api/test_ppe_budget_api.py tests/api/test_ppe_api.py tests/api/test_ppe_stock_movements_api.py tests/api/test_ppe_reorder_service.py -q
```
Expected: all green (exit 0). Judge by `$LASTEXITCODE` (Out-File may truncate the summary line).

- [ ] **Step 2: ruff + black on changed backend files**

```
& "…python.exe" -m ruff check backend/app/models/ppe.py backend/app/models/models.py backend/app/models/ppe_registry.py backend/app/modules/ppe/budget.py backend/app/api/routes/ppe.py backend/app/schemas/ppe.py backend/app/migrations/versions/20260705_wa09_ppe_safety_budget.py tests/api/test_ppe_budget_*.py
& "…python.exe" -m black backend/app/modules/ppe/budget.py backend/app/api/routes/ppe.py backend/app/schemas/ppe.py backend/app/models/ppe.py tests/api/test_ppe_budget_*.py
```
Fix any findings; re-run the affected pytest file if black reformats a test with substring assertions.

- [ ] **Step 3: OpenAPI baseline re-snapshot**

```
$env:PYTHONPATH="backend"; & "…python.exe" scripts/ci/check_openapi_snapshot.py --snapshot
```
Then verify additive-only: `& "…python.exe" scripts/ci/check_openapi_snapshot.py --compare` → EXIT 0 (`✓ ARCH-4 unchanged` / additive). New routes: `POST/GET /ppe/budgets`, `GET/PATCH/DELETE /ppe/budgets/{id}`; new schemas: `PPESafetyBudget{Create,Update,Read,Page,Detail}`, `PPEBudgetCategoryActualRead`; `unit_cost` added to batch schemas. Record the route/schema counts (before → after) for the handoff.

- [ ] **Step 4: PG16 gate (migration `wa09`)**

```
& "…python.exe" scripts/ci/local_gate.py --db-only
```
Expected: alembic `upgrade heads` (incl. `wa09`) + downgrade round-trip + enum-parity green on PG16 (Docker). If Docker unavailable, note it and rely on CI; otherwise a throwaway `postgres:16` + `alembic upgrade heads → downgrade -1 → upgrade heads` round-trip.

- [ ] **Step 5: Frontend gates**

```
cd "…/frontend" && npx vitest run && npx tsc --noEmit && npm run build
```
Expected: full vitest green (incl. OpsPages fixed), tsc 0, build exit 0. (Full `vitest run` can flake under parallelism — re-check any suspect file in isolation before treating as real.)

- [ ] **Step 6: Update docs**

- `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` — P10-06 row: append a «бюджет безопасности» clause (СИЗ scope: `PPESafetyBudget` + `unit_cost`, procurement plan-vs-actual + category breakdown, `wa09`); change the trailing `**Остаётся:**` to note the cross-domain §12.4 contour (training/medical/events/reimbursements/branch-analytics) remains as a separate sub-project. Update the Summary line accordingly.
- `CHANGELOG.md` — prepend a `2026-07-05 … P10-06 бюджет безопасности` entry (СИЗ scope; new model/migration/routes; computed actual; deferred cross-domain).
- `AI_IMPLEMENTATION_REPORT.md` — prepend a handoff block: decisions (СИЗ-only / procurement / batch unit_cost / tenant-wide period), architecture (`wa09`, computed actual over receipts, invariant untouched), verification (pytest/OpenAPI counts/PG16/frontend), deferred (§12.4 cross-domain, branch analytics, consumption cost), next step (next partial: P10-03 medical contingent or P10-07 report-builder), branch state (NOT merged; base=main).

- [ ] **Step 7: Commit**

```bash
git add docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md CHANGELOG.md AI_IMPLEMENTATION_REPORT.md docs/stabilization/openapi_routes_baseline.json docs/superpowers/plans/2026-07-05-p10-06-ppe-safety-budget.md
git commit -m "docs(p10-06): roadmap + changelog + handoff + OpenAPI baseline for safety budget"
```

---

## Self-Review

**1. Spec coverage:**
- `PPESafetyBudget` (period + planned, tenant-wide) → Task 1. ✅
- `PPEStockBatch.unit_cost` → Tasks 1 (model/migration), 2 (schema), 5 (create wiring). ✅
- Procurement actual = Σ receipt qty × unit_cost, category breakdown, unpriced counted → Task 4. ✅
- `wa09` additive migration → Task 1; PG16 gate → Task 7. ✅
- 5 routes behind `warehouse` flag, Manager/Editor, detail returns plan/actual/remaining/breakdown/unpriced → Task 5. ✅
- Frontend section + unit_cost field + OpsPages fix → Task 6. ✅
- Honest-stock invariant (no mutator; computed actual) → Tasks 4 (compute is read-only) & 5 (batch create unchanged mutator path). ✅
- OpenAPI/PG16/ruff-black/regression gates → Task 7. ✅
- Deferred items (§12.4 cross-domain, branch analytics, consumption) → not implemented; documented Task 7. ✅

**2. Placeholder scan:** No TBD/TODO; backend steps have complete code. Task 6 WarehousePage section is described with exact required strings (the page is a 995-line single-file per house convention; the implementer mirrors the existing «Поставщики» section) — acceptable, and its test asserts the required strings.

**3. Type consistency:** `PPESafetyBudget` fields (name/period_start/period_end/planned_amount/notes) identical across model, migration, schemas, service, routes, and tests. `BudgetActual`/`BudgetCategoryActual` dataclasses ↔ `PPESafetyBudgetDetail`/`PPEBudgetCategoryActualRead` schemas ↔ frontend `BudgetDetailDto`/`BudgetCategoryActualDto` all carry the same field names (`actual_total`, `remaining`, `by_category`, `priced_receipt_count`, `unpriced_receipt_count`, `{category, amount}`). Service function signatures (`create_budget`, `compute_budget_actual`, etc.) match their imports in routes and tests. `unit_cost` consistent (model/migration/schema/frontend).

## Anti-gotchas
- **Register `PPESafetyBudget` in all THREE files** (`ppe.py` define, `models.py` re-export+`__all__`, `ppe_registry.py` re-export+`__all__`) — miss one and imports fail at boot.
- **Only `kind="receipt"` & `quantity_delta>0`** count in actual — issue/writeoff/adjustment/transfer must not (Task 4 test covers each).
- **Period boundary:** `occurred_at` is datetime, period is dates — use `time.min`/`time.max` so last-day receipts are included.
- **Unpriced receipts excluded from total but counted** — never silently treat null cost as 0.
- **Money is `Numeric(14,2)`** typed `float`; ORM returns `Decimal` → cast with `float(...)` in compute and detail (tests use `float(...)`).
- **`wa09` chains from `wa08`** (single head in main); additive; honest downgrade; validated only by PG16 gate (SQLite alembic n/a).
- **OpenAPI baseline** must be re-snapshotted (Task 7) or ARCH-4 goes red; script needs `$env:PYTHONPATH="backend"`.
- **OpsPages.test.tsx** on this branch is the pre-fix version — re-apply the full warehouse mock + `listBudgets` (Task 6), else full vitest is red.
- **Backend tests via PowerShell**, global Python313, one invocation, timeout 600000, batches ≤4 (Git-Bash segfaults; cold import ~2-3 min). Judge by `$LASTEXITCODE`.
