# PPE Warehouse Skeleton (W-A · TZ-3.2-V11-01) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a minimal, additive PPE warehouse (склад СИЗ) skeleton — stock batches with certificates + aggregate stock levels — exposed under `/api/v1/ppe/stock/*`, per-tenant feature-gated, and wire the existing `WarehousePage` to real data, flipping `TZ-3.2-V11-01` to `done`.

**Architecture:** New tenant-scoped ORM model `PPEStockBatch` (table `ppe_stock_batch`) referencing the existing `PPEItem` catalogue; additive Alembic migration; new Pydantic schemas; new endpoints appended to the existing `/ppe` router (no route-group change) reusing the shared `compute_list_etag` conditional-GET helper; a minimal per-tenant `warehouse` feature gate built on the existing `Feature`/`FeatureEnablement` models (default-on, disable via `FeatureEnablement.on=False` → 404); the existing `WarehousePage.tsx` façade is repointed from `opsApi.getPpeOverview()` to a new `warehouseApi`. The orphan `WarehousePPE` stub is left untouched (additive rule).

**Tech Stack:** Python 3.12.12 (canonical; local may be 3.13 — see `CLAUDE.md`), FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2; React 18 + TS + Vite + Vitest.

---

## Source spec

`docs/superpowers/specs/2026-05-29-tz-completeness-roadmap-design.md` §5. Canon: `docs/spec/TZ_FULL_UNIFIED.md` B.11 / vNext §12.3. Matrix row: `TZ-3.2-V11-01` (`missing` → target `done`).

## Setup (do once before Task 1)

- [ ] **Create the working branch**

```bash
git checkout -b feat/wa-ppe-warehouse-skeleton
```

- [ ] **Confirm the Python interpreter** (per `CLAUDE.md`)

```bash
python3.12 --version 2>/dev/null && echo "3.12 ok" || python --version
```
Use `python3.12 -m pytest …` if available; else `python -m pytest …` (Windows: `py -3 -m pytest …`). Below, commands say `python -m pytest` — substitute the detected interpreter. CI on 3.12.12 is canonical.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/models/models.py` | Modify (add class after `PPEIssue`, ~line 1361) | `PPEStockBatch` ORM model |
| `backend/app/models/ppe_registry.py` | Modify | Re-export `PPEStockBatch` |
| `backend/app/migrations/versions/20260529_wa01_ppe_stock_batch.py` | Create | Additive `create_table ppe_stock_batch` |
| `backend/app/schemas/ppe.py` | Modify | `PPEStockBatch*` + `PPEStockLevel*` schemas |
| `backend/app/api/routes/ppe.py` | Modify | `require_warehouse_enabled` gate + `/stock/*` endpoints |
| `tests/api/test_ppe_warehouse_api.py` | Create | CRUD + tenant isolation + feature-off + levels |
| `tests/api/test_ppe_warehouse_cache_etag_contract.py` | Create | ETag conditional-GET contract |
| `backend/tests/test_wa01_ppe_stock_batch_migration.py` | Create | AST pin: migration shape (runs on 3.13) |
| `frontend/src/api/warehouse.ts` | Create | `warehouseApi` client |
| `frontend/src/pages/warehouse/WarehousePage.tsx` | Modify | Repoint façade → real warehouse data |
| `frontend/src/__tests__/WarehousePage.test.tsx` | Create/Modify | Vitest for real data path |
| `docs/audit/TZ_COVERAGE_MATRIX.md` | Modify | Flip `TZ-3.2-V11-01` |
| `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` | Modify | Mark W-A склад item |
| `AI_IMPLEMENTATION_REPORT.md` | Modify | New handoff block |

---

## Task 1: `PPEStockBatch` ORM model

**Files:**
- Modify: `backend/app/models/models.py` (insert after `PPEIssue.__table_args__`, ~line 1361)
- Modify: `backend/app/models/ppe_registry.py`
- Test: `backend/tests/test_wa01_ppe_stock_batch_migration.py` (model part)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_wa01_ppe_stock_batch_migration.py`:

```python
"""Pin: PPEStockBatch model + ppe_stock_batch migration shape (W-A / TZ-3.2-V11-01)."""
from __future__ import annotations


def test_ppe_stock_batch_model_table_and_columns() -> None:
    from app.models.models import PPEStockBatch

    assert PPEStockBatch.__tablename__ == "ppe_stock_batch"
    cols = set(PPEStockBatch.__table__.columns.keys())
    # tenant base + soft delete + version + own columns
    assert {
        "id", "tenant_id", "version", "created_at", "updated_at", "deleted_at",
        "item_id", "batch_no", "quantity", "received_at",
        "certificate_no", "certificate_expires_at", "location",
    } <= cols
    uniques = {c.name for c in PPEStockBatch.__table__.constraints if c.name}
    assert "uq_ppe_stock_batch_item_no" in uniques


def test_ppe_stock_batch_reexported_from_registry() -> None:
    from app.models.ppe_registry import PPEStockBatch  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_wa01_ppe_stock_batch_migration.py -q`
Expected: FAIL — `ImportError: cannot import name 'PPEStockBatch'`.

- [ ] **Step 3: Add the model**

In `backend/app/models/models.py`, immediately after the `PPEIssue` class (after its `__table_args__`, ~line 1361), add:

```python
class PPEStockBatch(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "ppe_stock_batch"

    item_id: Mapped[str] = mapped_column(
        ForeignKey("ppeitem.id", ondelete="CASCADE"), nullable=False, index=True
    )
    batch_no: Mapped[str] = mapped_column(String(128), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    certificate_no: Mapped[str | None] = mapped_column(String(128), nullable=True)
    certificate_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    item: Mapped[PPEItem] = relationship("PPEItem")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "item_id", "batch_no", name="uq_ppe_stock_batch_item_no"
        ),
        Index("ix_ppe_stock_batch_item", "tenant_id", "item_id"),
    )
```

`Date`, `Integer`, `String`, `ForeignKey`, `UniqueConstraint`, `Index`, `Mapped`, `mapped_column`, `relationship`, `date` are already imported in `models.py` (used by `Journal`/`PPEItem`). Do **not** add imports unless a NameError appears.

- [ ] **Step 4: Re-export from the registry**

In `backend/app/models/ppe_registry.py`, replace the import + `__all__`:

```python
from app.models.models import (
    PPEIssue,
    PPEIssueStatus,
    PPEItem,
    PPEItemCategory,
    PPEStockBatch,
    WarehousePPE,
)

__all__ = [
    "PPEItem",
    "PPEItemCategory",
    "PPEIssue",
    "PPEIssueStatus",
    "PPEStockBatch",
    "WarehousePPE",
]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_wa01_ppe_stock_batch_migration.py -q`
Expected: 2 passed (the migration-shape test added in Task 2 is not yet present).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/models.py backend/app/models/ppe_registry.py backend/tests/test_wa01_ppe_stock_batch_migration.py
git commit -m "feat(ppe): add PPEStockBatch model for warehouse skeleton (TZ-3.2-V11-01)"
```

---

## Task 2: Additive Alembic migration `ppe_stock_batch`

**Files:**
- Create: `backend/app/migrations/versions/20260529_wa01_ppe_stock_batch.py`
- Test: `backend/tests/test_wa01_ppe_stock_batch_migration.py` (migration part)

- [ ] **Step 1: Determine the current head**

Run: `cd backend && python -m alembic heads`
Expected: prints one or more revision ids (repo has multiple heads by design — prod runs `upgrade heads`). Record the most recent head id. If unsure, use the merge linchpin `20260416_next69_merge_heads` (guaranteed ancestor that already contains `tenant` and `ppeitem`). Use the recorded id as `<HEAD>` below.

- [ ] **Step 2: Write the failing migration-shape test**

Append to `backend/tests/test_wa01_ppe_stock_batch_migration.py`:

```python
import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260529_wa01_ppe_stock_batch.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("wa01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260529_wa01_ppe_stock_batch"
    assert isinstance(mod.down_revision, str) and mod.down_revision
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
    src = _MIGRATION.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "ppe_stock_batch"' in src
    assert 'op.drop_table("ppe_stock_batch")' in src
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_wa01_ppe_stock_batch_migration.py -q`
Expected: FAIL — file not found / module load error for the migration.

- [ ] **Step 4: Write the migration**

Create `backend/app/migrations/versions/20260529_wa01_ppe_stock_batch.py` (replace `<HEAD>` with the id from Step 1):

```python
"""ppe stock batch skeleton (W-A / TZ-3.2-V11-01 / vNext §12.3)

Additive: creates ppe_stock_batch (PPE warehouse batches with certificate
metadata). Mirrors TenantBaseModel + SoftDeleteMixin columns. No data
backfill. The legacy orphan `warehouseppe` table is intentionally left
untouched.

Revision ID: 20260529_wa01_ppe_stock_batch
Revises: <HEAD>
Create Date: 2026-05-29 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260529_wa01_ppe_stock_batch"
down_revision = "<HEAD>"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_stock_batch",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("item_id", sa.String(length=36), nullable=False),
        sa.Column("batch_no", sa.String(length=128), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("received_at", sa.Date(), nullable=True),
        sa.Column("certificate_no", sa.String(length=128), nullable=True),
        sa.Column("certificate_expires_at", sa.Date(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["item_id"], ["ppeitem.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "item_id", "batch_no", name="uq_ppe_stock_batch_item_no"
        ),
    )
    op.create_index(
        op.f("ix_ppe_stock_batch_tenant_id"), "ppe_stock_batch", ["tenant_id"]
    )
    op.create_index(
        "ix_ppe_stock_batch_item", "ppe_stock_batch", ["tenant_id", "item_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ppe_stock_batch_item", table_name="ppe_stock_batch")
    op.drop_index(op.f("ix_ppe_stock_batch_tenant_id"), table_name="ppe_stock_batch")
    op.drop_table("ppe_stock_batch")
```

- [ ] **Step 5: Run shape test + apply migration on the test DB**

Run: `python -m pytest backend/tests/test_wa01_ppe_stock_batch_migration.py -q`
Expected: 4 passed.

Run: `cd backend && python -m alembic upgrade heads`
Expected: applies `20260529_wa01_ppe_stock_batch` with no error (creates `ppe_stock_batch`). If `python -m alembic` is not wired, the table is also created by the test DB bootstrap (`Base.metadata.create_all`) — the API tests in Task 7/8 are the functional proof. Note any version mismatch per `CLAUDE.md`; do not abort.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260529_wa01_ppe_stock_batch.py backend/tests/test_wa01_ppe_stock_batch_migration.py
git commit -m "feat(db): additive migration for ppe_stock_batch (TZ-3.2-V11-01)"
```

---

## Task 3: Pydantic schemas

**Files:**
- Modify: `backend/app/schemas/ppe.py`
- Test: covered functionally by Task 8 (no standalone schema test needed — schemas are validated through the API)

- [ ] **Step 1: Extend the imports**

At the top of `backend/app/schemas/ppe.py`, change:

```python
from datetime import datetime
```
to:
```python
from datetime import date, datetime
```

- [ ] **Step 2: Append the schemas** (end of `backend/app/schemas/ppe.py`)

```python
class PPEStockBatchCreate(BaseSchema):
    item_id: str
    batch_no: str
    quantity: int = Field(default=0, ge=0)
    received_at: date | None = None
    certificate_no: str | None = None
    certificate_expires_at: date | None = None
    location: str | None = None


class PPEStockBatchUpdate(BaseSchema):
    batch_no: str | None = None
    quantity: int | None = Field(default=None, ge=0)
    received_at: date | None = None
    certificate_no: str | None = None
    certificate_expires_at: date | None = None
    location: str | None = None


class PPEStockBatchRead(BaseSchema):
    id: str
    item_id: str
    batch_no: str
    quantity: int
    received_at: date | None
    certificate_no: str | None
    certificate_expires_at: date | None
    location: str | None
    created_at: datetime
    updated_at: datetime


class PPEStockBatchPage(BaseSchema):
    items: list[PPEStockBatchRead]
    total: int


class PPEStockLevelRead(BaseSchema):
    item_id: str
    item_name: str
    total_quantity: int
    batch_count: int
    nearest_certificate_expiry: date | None


class PPEStockLevelPage(BaseSchema):
    items: list[PPEStockLevelRead]
    total: int
```

- [ ] **Step 3: Verify import**

Run: `python -c "from app.schemas.ppe import PPEStockBatchCreate, PPEStockBatchPage, PPEStockLevelPage; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/schemas/ppe.py
git commit -m "feat(ppe): schemas for stock batches and stock levels"
```

---

## Task 4: Per-tenant `warehouse` feature gate

**Files:**
- Modify: `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_warehouse_api.py` (the feature-off case, Task 8)

- [ ] **Step 1: Add imports + gate** (in `backend/app/api/routes/ppe.py`)

After the existing model import block, add:

```python
from app.models.feature import Feature, FeatureEnablement
from app.models.ppe_registry import PPEStockBatch
```
(`PPEItem`, `PPEIssue`, `PPEIssueStatus` stay as the existing `from app.models.ppe_registry import ...` line — add `PPEStockBatch` there if you prefer a single import line.)

After the `EditorAccess` definition (~line 57), add the gate:

```python
async def require_warehouse_enabled(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Per-tenant gate for the warehouse (склад СИЗ) feature.

    Default-ON: absent FeatureEnablement row → allowed. Disable per tenant by
    inserting/updating FeatureEnablement(on=False) for Feature(code="warehouse").
    Additive — does not touch existing PPE endpoints.
    """
    stmt = (
        select(FeatureEnablement.on)
        .join(Feature, Feature.id == FeatureEnablement.feature_id)
        .where(
            Feature.code == "warehouse",
            FeatureEnablement.tenant_id == tenant.id,
        )
    )
    enabled = (await session.execute(stmt)).scalar_one_or_none()
    if enabled is False:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_problem_detail(
                code="FEATURE_DISABLED",
                message="warehouse feature is disabled for this tenant",
                error_type="ppe",
            ),
        )


WarehouseGate = Annotated[None, Depends(require_warehouse_enabled)]
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.api.routes.ppe import require_warehouse_enabled, WarehouseGate; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/routes/ppe.py
git commit -m "feat(ppe): per-tenant warehouse feature gate (default-on)"
```

---

## Task 5: Stock-batch endpoints (list + create + get + patch)

**Files:**
- Modify: `backend/app/api/routes/ppe.py` (append after `update_issue`)
- Test: Task 7 (ETag) + Task 8 (CRUD)

- [ ] **Step 1: Add the schema imports**

Extend the existing `from app.schemas.ppe import (...)` block with:

```python
    PPEStockBatchCreate,
    PPEStockBatchPage,
    PPEStockBatchRead,
    PPEStockBatchUpdate,
    PPEStockLevelPage,
    PPEStockLevelRead,
```

- [ ] **Step 2: Append the helper + endpoints** (end of `backend/app/api/routes/ppe.py`)

```python
async def _get_batch(session: AsyncSession, tenant: Tenant, batch_id: str) -> PPEStockBatch:
    stmt = select(PPEStockBatch).where(
        PPEStockBatch.id == batch_id,
        PPEStockBatch.tenant_id == tenant.id,
        PPEStockBatch.deleted_at.is_(None),
    )
    batch = (await session.execute(stmt)).scalar_one_or_none()
    if batch is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE stock batch not found")
    return batch


@router.get("/stock/batches", response_model=PPEStockBatchPage)
async def list_stock_batches(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    _gate: WarehouseGate,
    item_id: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PPEStockBatchPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    stmt = select(PPEStockBatch).where(
        PPEStockBatch.tenant_id == tenant.id, PPEStockBatch.deleted_at.is_(None)
    )
    if item_id:
        stmt = stmt.where(PPEStockBatch.item_id == item_id)
    stmt = stmt.order_by(PPEStockBatch.batch_no.asc()).limit(limit).offset(offset)
    batches = list((await session.execute(stmt)).scalars().all())

    count_stmt = select(func.count()).where(
        PPEStockBatch.tenant_id == tenant.id, PPEStockBatch.deleted_at.is_(None)
    )
    if item_id:
        count_stmt = count_stmt.where(PPEStockBatch.item_id == item_id)
    total = (await session.execute(count_stmt)).scalar_one()

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=batches,
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
    return PPEStockBatchPage(
        items=[PPEStockBatchRead.model_validate(b) for b in batches], total=total
    )


@router.post(
    "/stock/batches", response_model=PPEStockBatchRead, status_code=status.HTTP_201_CREATED
)
@audit_operation("create", "ppe_stock_batch")
async def create_stock_batch(
    payload: PPEStockBatchCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
    _gate: WarehouseGate,
) -> PPEStockBatchRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    # validate the referenced catalogue item belongs to the tenant
    await _get_item(session, tenant, payload.item_id)

    batch = PPEStockBatch(
        tenant_id=tenant.id,
        item_id=payload.item_id,
        batch_no=payload.batch_no,
        quantity=payload.quantity,
        received_at=payload.received_at,
        certificate_no=payload.certificate_no,
        certificate_expires_at=payload.certificate_expires_at,
        location=payload.location,
    )
    session.add(batch)
    await session.flush()
    await session.refresh(batch)
    return PPEStockBatchRead.model_validate(batch)


@router.get("/stock/batches/{batch_id}", response_model=PPEStockBatchRead)
async def get_stock_batch(
    batch_id: str,
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    _gate: WarehouseGate,
) -> PPEStockBatchRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    batch = await _get_batch(session, tenant, batch_id)
    return PPEStockBatchRead.model_validate(batch)


@router.patch("/stock/batches/{batch_id}", response_model=PPEStockBatchRead)
@audit_operation("update", "ppe_stock_batch")
async def update_stock_batch(
    batch_id: str,
    payload: PPEStockBatchUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
    _gate: WarehouseGate,
) -> PPEStockBatchRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    batch = await _get_batch(session, tenant, batch_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(batch, field, value)
    await session.flush()
    await session.refresh(batch)
    return PPEStockBatchRead.model_validate(batch)
```

- [ ] **Step 3: Smoke-import the router**

Run: `python -c "from app.api.routes.ppe import router; print(sorted({r.path for r in router.routes}))"`
Expected: list includes `/ppe/stock/batches` and `/ppe/stock/batches/{batch_id}`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/routes/ppe.py
git commit -m "feat(ppe): stock-batch CRUD endpoints with ETag conditional-GET"
```

---

## Task 6: Stock-levels aggregate endpoint

**Files:**
- Modify: `backend/app/api/routes/ppe.py` (append after `update_stock_batch`)
- Test: Task 8

- [ ] **Step 1: Append the endpoint**

```python
@router.get("/stock/levels", response_model=PPEStockLevelPage)
async def list_stock_levels(
    tenant: TenantDep,
    session: SessionDep,
    access: ManagerAccess,
    _gate: WarehouseGate,
) -> PPEStockLevelPage:
    TenantContextValidator.ensure_tenant_context(tenant)

    agg_stmt = (
        select(
            PPEStockBatch.item_id,
            func.coalesce(func.sum(PPEStockBatch.quantity), 0),
            func.count(PPEStockBatch.id),
            func.min(PPEStockBatch.certificate_expires_at),
        )
        .where(
            PPEStockBatch.tenant_id == tenant.id,
            PPEStockBatch.deleted_at.is_(None),
        )
        .group_by(PPEStockBatch.item_id)
    )
    rows = (await session.execute(agg_stmt)).all()

    names: dict[str, str] = {}
    item_ids = [row[0] for row in rows]
    if item_ids:
        name_rows = (
            await session.execute(
                select(PPEItem.id, PPEItem.name).where(PPEItem.id.in_(item_ids))
            )
        ).all()
        names = {item_id: name for item_id, name in name_rows}

    levels = [
        PPEStockLevelRead(
            item_id=row[0],
            item_name=names.get(row[0], ""),
            total_quantity=int(row[1] or 0),
            batch_count=int(row[2] or 0),
            nearest_certificate_expiry=row[3],
        )
        for row in rows
    ]
    return PPEStockLevelPage(items=levels, total=len(levels))
```

- [ ] **Step 2: Smoke-import**

Run: `python -c "from app.api.routes.ppe import router; print('/ppe/stock/levels' in {r.path for r in router.routes})"`
Expected: `True`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/routes/ppe.py
git commit -m "feat(ppe): stock-levels aggregate endpoint"
```

---

## Task 7: ETag conditional-GET contract test

**Files:**
- Create: `tests/api/test_ppe_warehouse_cache_etag_contract.py`

- [ ] **Step 1: Write the test**

```python
"""HTTP cache (ETag / If-None-Match) contract for /api/v1/ppe/stock/batches
(W-A · TZ-3.2-V11-01). Mirrors tests/api/test_ppe_prescriptions_cache_etag_contract.py.
"""
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


async def _seed_batch(
    async_client: AsyncClient, headers: dict, *, item_id: str, batch_no: str, quantity: int = 10
) -> dict:
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": batch_no, "quantity": quantity},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_batches_hit_returns_304(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")

    first = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert first.status_code == status.HTTP_200_OK
    etag = first.headers["ETag"]

    second = await async_client.get(
        "/api/v1/ppe/stock/batches", headers={**headers, "If-None-Match": etag}
    )
    assert second.status_code == status.HTTP_304_NOT_MODIFIED
    assert second.headers["ETag"] == etag
    assert second.content == b""


@pytest.mark.asyncio
async def test_batches_miss_with_bogus_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")

    resp = await async_client.get(
        "/api/v1/ppe/stock/batches", headers={**headers, "If-None-Match": '"stale"'}
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["items"]


@pytest.mark.asyncio
async def test_batches_etag_changes_after_create(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")
    first = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    initial = first.headers["ETag"]

    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-2")
    second = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert second.headers["ETag"] != initial


@pytest.mark.asyncio
async def test_batches_filter_distinct_etag(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)
    await _seed_batch(async_client, headers, item_id=item_id, batch_no="B-1")

    unfiltered = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    filtered = await async_client.get(
        f"/api/v1/ppe/stock/batches?item_id={item_id}", headers=headers
    )
    assert unfiltered.headers["ETag"] != filtered.headers["ETag"]


@pytest.mark.asyncio
async def test_batches_cross_tenant_anti_leak(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()

    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    item_a = await _seed_item(async_client, headers_a, name="Каска")
    await _seed_batch(async_client, headers_a, item_id=item_a, batch_no="B-1")
    resp_a = await async_client.get("/api/v1/ppe/stock/batches", headers=headers_a)
    etag_a = resp_a.headers["ETag"]

    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    item_b = await _seed_item(async_client, headers_b, name="Каска")
    await _seed_batch(async_client, headers_b, item_id=item_b, batch_no="B-1")
    resp_b = await async_client.get("/api/v1/ppe/stock/batches", headers=headers_b)
    assert resp_b.headers["ETag"] != etag_a
```

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/api/test_ppe_warehouse_cache_etag_contract.py -q`
Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_ppe_warehouse_cache_etag_contract.py
git commit -m "test(ppe): ETag contract for /ppe/stock/batches"
```

---

## Task 8: API test — CRUD, levels, tenant isolation, feature gate

**Files:**
- Create: `tests/api/test_ppe_warehouse_api.py`

- [ ] **Step 1: Write the test**

```python
"""API contract for the PPE warehouse skeleton (W-A · TZ-3.2-V11-01):
CRUD, stock-levels aggregate, tenant isolation, per-tenant feature gate.
"""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from app.models.tenanting import Tenant
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


@pytest.mark.asyncio
async def test_create_list_get_patch_batch(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers)

    created = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={
            "item_id": item_id,
            "batch_no": "B-100",
            "quantity": 25,
            "certificate_no": "CERT-1",
        },
        headers=headers,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    batch_id = created.json()["id"]
    assert created.json()["quantity"] == 25

    listed = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(b["id"] == batch_id for b in listed.json()["items"])

    fetched = await async_client.get(f"/api/v1/ppe/stock/batches/{batch_id}", headers=headers)
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["certificate_no"] == "CERT-1"

    patched = await async_client.patch(
        f"/api/v1/ppe/stock/batches/{batch_id}", json={"quantity": 5}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["quantity"] == 5


@pytest.mark.asyncio
async def test_create_batch_unknown_item_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": "does-not-exist", "batch_no": "B-1", "quantity": 1},
        headers=headers,
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_stock_levels_aggregate(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _seed_item(async_client, headers, name="Перчатки")
    for no, qty in (("B-1", 10), ("B-2", 7)):
        resp = await async_client.post(
            "/api/v1/ppe/stock/batches",
            json={"item_id": item_id, "batch_no": no, "quantity": qty},
            headers=headers,
        )
        assert resp.status_code == status.HTTP_201_CREATED, resp.text

    levels = await async_client.get("/api/v1/ppe/stock/levels", headers=headers)
    assert levels.status_code == status.HTTP_200_OK
    body = levels.json()
    row = next(r for r in body["items"] if r["item_id"] == item_id)
    assert row["total_quantity"] == 17
    assert row["batch_count"] == 2
    assert row["item_name"] == "Перчатки"


@pytest.mark.asyncio
async def test_batches_tenant_isolation(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        await session.commit()
    headers_a = await make_auth_headers(RoleEnum.ADMIN)
    item_a = await _seed_item(async_client, headers_a)
    resp = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_a, "batch_no": "B-1", "quantity": 3},
        headers=headers_a,
    )
    batch_a = resp.json()["id"]

    headers_b = await make_auth_headers(RoleEnum.ADMIN, tenant="beta")
    # tenant B cannot see tenant A's batch
    listed_b = await async_client.get("/api/v1/ppe/stock/batches", headers=headers_b)
    assert all(b["id"] != batch_a for b in listed_b.json()["items"])
    # tenant B cannot fetch it by id
    fetched_b = await async_client.get(
        f"/api/v1/ppe/stock/batches/{batch_a}", headers=headers_b
    )
    assert fetched_b.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_warehouse_feature_disabled_returns_404(
    async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tenant_id = tenant.id if isinstance(tenant, Tenant) else (
            (await session.execute(select(Tenant.id))).scalars().first()
        )
        feature = Feature(code="warehouse", title="Склад СИЗ")
        session.add(feature)
        await session.flush()
        session.add(
            FeatureEnablement(tenant_id=tenant_id, feature_id=feature.id, on=False)
        )
        await session.commit()

    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/batches", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.json()["detail"]["code"] == "FEATURE_DISABLED"
```

> Note: if `data_factory.ensure_tenant(...)` does not return the Tenant object, the test resolves the id via `select(Tenant.id)` — keep whichever branch the local factory supports; both are present so the test is robust to the factory's return contract.

- [ ] **Step 2: Run the test**

Run: `python -m pytest tests/api/test_ppe_warehouse_api.py -q`
Expected: 5 passed. If the feature-gate test fails on `detail["code"]`, inspect the actual `api_problem_detail` shape and align the assertion (it nests under `detail`).

- [ ] **Step 3: Run the whole warehouse suite together**

Run: `python -m pytest tests/api/test_ppe_warehouse_api.py tests/api/test_ppe_warehouse_cache_etag_contract.py backend/tests/test_wa01_ppe_stock_batch_migration.py -q`
Expected: all pass (11 tests). Note Py version per `CLAUDE.md`.

- [ ] **Step 4: Commit**

```bash
git add tests/api/test_ppe_warehouse_api.py
git commit -m "test(ppe): warehouse CRUD, levels, isolation, feature-gate"
```

---

## Task 9: Frontend — `warehouseApi` + repoint `WarehousePage`

**Files:**
- Create: `frontend/src/api/warehouse.ts`
- Modify: `frontend/src/pages/warehouse/WarehousePage.tsx`

- [ ] **Step 1: Create the api client**

`frontend/src/api/warehouse.ts`:

```ts
import { apiClient } from "@/api/client";

export type StockBatchDto = {
  id: string;
  item_id: string;
  batch_no: string;
  quantity: number;
  received_at?: string | null;
  certificate_no?: string | null;
  certificate_expires_at?: string | null;
  location?: string | null;
  created_at: string;
  updated_at: string;
};

export type StockLevelDto = {
  item_id: string;
  item_name: string;
  total_quantity: number;
  batch_count: number;
  nearest_certificate_expiry?: string | null;
};

type PageResponse<T> = { items: T[]; total: number };

export const warehouseApi = {
  async listBatches(): Promise<StockBatchDto[]> {
    const response = await apiClient.get<PageResponse<StockBatchDto>>("/ppe/stock/batches", {
      params: { limit: 100, offset: 0 }
    });
    return response.data.items ?? [];
  },
  async listLevels(): Promise<StockLevelDto[]> {
    const response = await apiClient.get<PageResponse<StockLevelDto>>("/ppe/stock/levels");
    return response.data.items ?? [];
  }
};
```

- [ ] **Step 2: Repoint `WarehousePage.tsx`**

Replace the data layer (imports, state, `load`, `rows`) so the page renders real stock levels + batches. Replace lines 1–77 of `frontend/src/pages/warehouse/WarehousePage.tsx` with:

```tsx
import { useEffect, useMemo, useState } from "react";

import { warehouseApi, type StockBatchDto, type StockLevelDto } from "@/api/warehouse";
import { EmptyState } from "@/components/common/EmptyState";
import { ErrorState } from "@/components/common/ErrorState";
import { LoadingScreen } from "@/components/common/LoadingScreen";
import { RegistryPageHeader } from "@/components/common/RegistryPageHeader";
import { StatusBadge } from "@/components/common/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { ApiError } from "@/types/dto/common";
import { formatDate } from "@/utils/datetime";

const WarehousePage = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [query, setQuery] = useState("");
  const [levels, setLevels] = useState<StockLevelDto[]>([]);
  const [batches, setBatches] = useState<StockBatchDto[]>([]);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const [levelsData, batchesData] = await Promise.all([
        warehouseApi.listLevels(),
        warehouseApi.listBatches()
      ]);
      setLevels(levelsData);
      setBatches(batchesData);
    } catch (err) {
      setError((err as ApiError) ?? { message: "Не удалось загрузить склад СИЗ" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const totalQuantity = useMemo(
    () => levels.reduce((sum, level) => sum + level.total_quantity, 0),
    [levels]
  );

  const rows = useMemo(() => {
    return levels.map((level) => {
      const status = level.total_quantity <= 0 ? "warning" : "ready";
      const searchBlob = [level.item_name, level.item_id].filter(Boolean).join(" ").toLowerCase();
      return {
        id: level.item_id,
        name: level.item_name,
        quantity: level.total_quantity,
        batchCount: level.batch_count,
        nearestExpiry: level.nearest_certificate_expiry ?? null,
        status,
        searchBlob
      };
    });
  }, [levels]);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return rows;
    return rows.filter((item) => item.searchBlob.includes(normalized));
  }, [query, rows]);
```

Then update the JSX (lines 79–155 originally) so the metric cards and table reflect levels/batches. Replace the three metric `<Card>` blocks' values with: positions = `levels.length`; total quantity = `totalQuantity`; batches = `batches.length`. Replace the table header cells with `Номенклатура / Остаток / Партий / Ближайшее истечение / Статус` and the body with:

```tsx
{filtered.map((item) => (
  <TableRow key={item.id}>
    <TableCell className="font-medium">{item.name}</TableCell>
    <TableCell>{item.quantity}</TableCell>
    <TableCell>{item.batchCount}</TableCell>
    <TableCell>{formatDate(item.nearestExpiry) || "—"}</TableCell>
    <TableCell><StatusBadge status={item.status} /></TableCell>
  </TableRow>
))}
```

Keep `RegistryPageHeader` title "Склад СИЗ"; set `actions={<Badge variant="secondary">Партий: {batches.length}</Badge>}`.

- [ ] **Step 3: Type-check + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint src/api/warehouse.ts src/pages/warehouse/WarehousePage.tsx`
Expected: clean (0 errors).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/warehouse.ts frontend/src/pages/warehouse/WarehousePage.tsx
git commit -m "feat(frontend): wire WarehousePage to /ppe/stock real data"
```

---

## Task 10: Frontend test for `WarehousePage`

**Files:**
- Create: `frontend/src/__tests__/WarehousePage.test.tsx`

- [ ] **Step 1: Write the test**

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import WarehousePage from "@/pages/warehouse/WarehousePage";
import { warehouseApi } from "@/api/warehouse";

vi.mock("@/api/warehouse", () => ({
  warehouseApi: {
    listLevels: vi.fn(),
    listBatches: vi.fn()
  }
}));

describe("WarehousePage", () => {
  it("renders stock levels from the warehouse API", async () => {
    (warehouseApi.listLevels as ReturnType<typeof vi.fn>).mockResolvedValue([
      { item_id: "i1", item_name: "Каска", total_quantity: 12, batch_count: 2, nearest_certificate_expiry: null }
    ]);
    (warehouseApi.listBatches as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: "b1", item_id: "i1", batch_no: "B-1", quantity: 12, created_at: "2026-05-29T00:00:00Z", updated_at: "2026-05-29T00:00:00Z" }
    ]);

    render(<WarehousePage />);

    await waitFor(() => expect(screen.getByText("Каска")).toBeInTheDocument());
    expect(screen.getByText("12")).toBeInTheDocument();
  });

  it("shows an empty state when there are no levels", async () => {
    (warehouseApi.listLevels as ReturnType<typeof vi.fn>).mockResolvedValue([]);
    (warehouseApi.listBatches as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    render(<WarehousePage />);

    await waitFor(() =>
      expect(screen.getByText(/В tenant ещё нет|Позиции не найдены/)).toBeInTheDocument()
    );
  });
});
```

> Adjust the empty-state matcher text to whatever the existing `EmptyState` copy is after the Task 9 edit.

- [ ] **Step 2: Run the test**

Run: `cd frontend && npx vitest run src/__tests__/WarehousePage.test.tsx`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/__tests__/WarehousePage.test.tsx
git commit -m "test(frontend): WarehousePage real-data render + empty state"
```

---

## Task 11: Docs, matrix, OpenAPI, handoff

**Files:**
- Modify: `docs/audit/TZ_COVERAGE_MATRIX.md`
- Modify: `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`
- Modify: `AI_IMPLEMENTATION_REPORT.md`
- Maybe Modify: `docs/openapi_snapshot_v01.json` / `docs/openapi.yaml`

- [ ] **Step 1: Flip the matrix row**

In `docs/audit/TZ_COVERAGE_MATRIX.md`, row `TZ-3.2-V11-01`, change `missing` → `done` and update the evidence columns to:
`backend/app/models/models.py (PPEStockBatch), backend/app/api/routes/ppe.py (/stock/*)` · `backend/app/migrations/versions/20260529_wa01_ppe_stock_batch.py` · frontend `frontend/src/pages/warehouse/WarehousePage.tsx` · tests `tests/api/test_ppe_warehouse_api.py, tests/api/test_ppe_warehouse_cache_etag_contract.py` · plan: "Skeleton shipped (batches+levels+certs); movements/suppliers/forecast → P10-06".

- [ ] **Step 2: Validate the matrix**

Run: `python scripts/audit/check_tz_coverage_matrix.py`
Expected: exit 0 (no validation errors). Fix column formatting if it complains.

- [ ] **Step 3: Update the roadmap + handoff**

In `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, mark the W-A склад item done (reference this plan + the spec). Prepend a `## Last Agent Handoff (…W-A ppe warehouse skeleton…)` block to `AI_IMPLEMENTATION_REPORT.md` summarizing files, tests, and the Next Step (W-A item #2: prescriptions lifecycle).

- [ ] **Step 4: Refresh OpenAPI snapshot if a test enforces it**

Run: `python -m pytest -q -k "openapi" tests/ 2>/dev/null || true`
If an OpenAPI snapshot/contract test fails because of the 5 new `/ppe/stock/*` operations, regenerate the snapshot per its docstring (commonly `python scripts/generate_openapi.py` or an env-gated `--snapshot-update`); inspect the failing test's instructions and follow them. If no such test exists, skip.

- [ ] **Step 5: Commit**

```bash
git add docs/audit/TZ_COVERAGE_MATRIX.md docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(ppe): close TZ-3.2-V11-01 (warehouse skeleton) in matrix + roadmap + handoff"
```

---

## Task 12: Final validation

- [ ] **Step 1: Backend targeted suite**

Run: `python -m pytest tests/api/test_ppe_warehouse_api.py tests/api/test_ppe_warehouse_cache_etag_contract.py tests/api/test_ppe_prescriptions_cache_etag_contract.py backend/tests/test_wa01_ppe_stock_batch_migration.py -q`
Expected: all pass (the pre-existing ppe ETag suite must stay green — regression guard). Record counts. Note Py version per `CLAUDE.md`; CI 3.12.12 is canonical.

- [ ] **Step 2: Frontend gates**

Run: `cd frontend && npx tsc --noEmit && npx vitest run src/__tests__/WarehousePage.test.tsx`
Expected: tsc clean; 2 vitest pass.

- [ ] **Step 3: Verify no regression in the existing /ppe routes**

Run: `python -m pytest tests/api -q -k "ppe"`
Expected: all ppe API/contract tests green (items/issues untouched).

- [ ] **Step 4: Push the branch (only when the user asks)**

```bash
git push -u origin feat/wa-ppe-warehouse-skeleton
```

---

## Self-review notes (author)

- **Spec coverage (§5):** schema (Task 1–2: item_id/batch_no/quantity/received_at/certificate_no/certificate_expires_at/location ✓); endpoints `/ppe/stock/batches` CRUD + `/stock/levels` (Task 5–6 ✓); ETag via `compute_list_etag` (Task 5/7 ✓); tenant isolation (Task 8 ✓); feature flag `warehouse` per-tenant (Task 4/8 ✓); frontend façade replaced (Task 9–10 ✓); matrix flip (Task 11 ✓); orphan `WarehousePPE` left untouched (stated in Task 2 migration docstring ✓). Deferred-with-rationale: movements/reservations/suppliers/deficit-forecast → P10-06 (noted in matrix plan cell).
- **Six questions (§36.4):** role (кладовщик/ОТ); scenario (учёт партий + сроки сертификатов); data (PPEItem + new batches); offline/error (ETag cache for reads; standard online writes); feedback (status badges, empty/error states reused from existing page); feature flag (`warehouse`, per-tenant, default-on, no global refactor). ✓
- **Type consistency:** `PPEStockBatch` / table `ppe_stock_batch` / schema `PPEStockBatch*` / route paths `/ppe/stock/batches`,`/ppe/stock/levels` used identically across Tasks 1–8; FE `StockBatchDto`/`StockLevelDto` mirror `PPEStockBatchRead`/`PPEStockLevelRead`. ✓
- **Open risk flagged for executor:** the exact nested shape of `api_problem_detail` (Task 8 Step 2) and the OpenAPI-snapshot test existence (Task 11 Step 4) are environment-verified at execution, with explicit fallback instructions — not placeholders.
