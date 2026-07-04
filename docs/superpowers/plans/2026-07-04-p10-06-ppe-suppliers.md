# P10-06 СИЗ склад — Suppliers (directory + provenance + reorder) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a normalized PPE supplier directory, batch/item supplier provenance, and a supplier-aware reorder draft on top of the honest-stock ledger — pure additive, the honest-stock invariant untouched.

**Architecture:** New `PPESupplier` entity (directory) + nullable `PPEStockBatch.supplier_id` (batch provenance) + nullable `PPEItem.preferred_supplier_id` (explicit reorder supplier), all via additive migration `wa08`. Supplier CRUD lives in a new `modules/ppe/suppliers.py`; the procurement layer extends `compute_shortages` (explicit→history supplier resolution) and adds a computed `GET /ppe/stock/reorder` draft grouped by supplier. Everything sits behind the `warehouse` feature flag.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 (async) / Alembic / Pydantic v2; React 18 / TypeScript / Vitest.

**Spec:** `docs/superpowers/specs/2026-07-04-p10-06-ppe-suppliers-design.md`

---

## Test execution environment (read once)

- This git-worktree has **no `.venv`/`node_modules`**. Backend tests run with the global interpreter:
  `C:\Users\karka\AppData\Local\Programs\Python\Python313\python.exe -m pytest <path> -q` **in PowerShell** (Git-Bash segfaults on pytest here). Local Py is 3.13; canon is 3.12.12 — note the mismatch, do not abort.
- **Cold app import is ~2-3 min.** Run each pytest/OpenAPI invocation with a **600000 ms timeout, ONCE, no retry loop** (the default 120 s Bash timeout kills the cold import mid-run and looks like a "hang").
- OpenAPI snapshot script needs `$env:PYTHONPATH="backend"`.
- `pythonpath = ["backend", "."]` is already set for pytest in `pyproject.toml`, so `from app.*` / `from tests.*` imports resolve.
- **black may reflow** `op.*(...)` calls in migrations — migration substring tests are whitespace-insensitive (`"".join(src.split())`); run black BEFORE asserting, or normalize.
- Frontend: `npm --prefix frontend run test`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`.
- Alembic does not run on SQLite here (historical JSONB in initial_schema) — the `wa08` round-trip is validated only by the **PG16 gate** (`python scripts/ci/local_gate.py --db-only`). Unit tests build the schema from ORM via `metadata.create_all`.

## File Structure

**Backend — create:**
- `backend/app/migrations/versions/20260704_wa08_ppe_supplier.py` — additive migration.
- `backend/app/modules/ppe/suppliers.py` — supplier CRUD service + exceptions.
- `tests/api/test_ppe_supplier_model.py` — ORM round-trip (needs tests/conftest.py DB fixtures).
- `backend/tests/test_wa08_ppe_supplier_migration.py` — migration metadata/shape (mirror `test_wa07_*`).
- `tests/api/test_ppe_suppliers_service.py` — CRUD service tests.
- `tests/api/test_ppe_suppliers_api.py` — CRUD API contract.
- `tests/api/test_ppe_supplier_provenance.py` — batch/item supplier wiring + transfer copy.
- `tests/api/test_ppe_reorder_service.py` — supplier resolution + reorder draft (unit + service).
- `tests/api/test_ppe_reorder_api.py` — `/stock/shortages` supplier fields + `/stock/reorder` contract.

**Backend — modify:**
- `backend/app/models/ppe.py` — `PPESupplier` class + two nullable FK columns.
- `backend/app/schemas/ppe.py` — supplier schemas, reorder schemas, extend batch/item/shortage schemas.
- `backend/app/modules/ppe/stock.py` — copy `supplier_id` in transfer; supplier resolution in `compute_shortages`; `ShortageRow` fields; reorder dataclasses + `build_reorder_draft`.
- `backend/app/api/routes/ppe.py` — supplier CRUD routes, reorder route, `_ppe_supplier_conflict`, wire `supplier_id`/`preferred_supplier_id`, shortage supplier fields.

**Frontend — modify:**
- `frontend/src/api/warehouse.ts` — supplier DTOs+methods, reorder DTO+method, extend batch/item/shortage DTOs.
- `frontend/src/pages/warehouse/WarehousePage.tsx` — suppliers section, batch supplier picker, deficit supplier column + inline picker, reorder view.
- `frontend/src/__tests__/WarehousePage.test.tsx` — vitest.

**Docs — modify (final task):**
- `docs/stabilization/openapi_routes_baseline.json` (re-snapshot), `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, `CHANGELOG.md`, `AI_IMPLEMENTATION_REPORT.md`.

---

## Task 1: `PPESupplier` model + provenance FK columns

**Files:**
- Modify: `backend/app/models/ppe.py`
- Test: `tests/api/test_ppe_supplier_model.py`  <!-- must live under tests/ so the sessionmaker/data_factory fixtures from tests/conftest.py are visible; backend/tests/ is a sibling dir and does NOT inherit them -->

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ppe_supplier_model.py
"""ORM round-trip for PPESupplier + batch/item provenance FKs (P10-06)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.ppe_registry import PPEItem, PPEStockBatch
from app.models.models import PPESupplier


@pytest.mark.asyncio
async def test_supplier_round_trip(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = PPESupplier(
            tenant_id=tenant.id,
            name="ООО Спецодежда",
            inn="7701234567",
            contact_email="sales@example.com",
            contact_phone="+7 495 000-00-00",
        )
        session.add(sup)
        await session.flush()

        item = PPEItem(tenant_id=tenant.id, name="Каска", preferred_supplier_id=sup.id)
        session.add(item)
        await session.flush()
        batch = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="B-1",
            quantity=5, location="A", supplier_id=sup.id,
        )
        session.add(batch)
        await session.flush()

        loaded = (
            await session.execute(select(PPESupplier).where(PPESupplier.id == sup.id))
        ).scalar_one()
        assert loaded.name == "ООО Спецодежда"
        assert loaded.inn == "7701234567"
        assert item.preferred_supplier_id == sup.id
        assert batch.supplier_id == sup.id


@pytest.mark.asyncio
async def test_supplier_name_unique_per_tenant(sessionmaker, data_factory):
    from sqlalchemy.exc import IntegrityError

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(PPESupplier(tenant_id=tenant.id, name="Дубль"))
        await session.flush()
        session.add(PPESupplier(tenant_id=tenant.id, name="Дубль"))
        with pytest.raises(IntegrityError):
            await session.flush()
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest backend/tests/test_ppe_supplier_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'PPESupplier'`.

- [ ] **Step 3: Add the model + FK columns**

In `backend/app/models/ppe.py`, add the `PPESupplier` class immediately **after** `class PPEItem(...)` (before `class PPEIssueStatus`):

```python
class PPESupplier(TenantBaseModel, SoftDeleteMixin):
    """PPE supplier directory (P10-06). Batches reference it via a nullable
    provenance FK; items reference it via ``preferred_supplier_id`` for the
    reorder draft. Name is unique per tenant (mirrors ``uq_ppe_item_name``)."""

    __tablename__ = "ppe_supplier"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str | None] = mapped_column(String(12), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_ppe_supplier_name"),
    )
```

In `class PPEItem`, add after `min_stock`:

```python
    preferred_supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppe_supplier.id", ondelete="SET NULL"), nullable=True, index=True
    )
```

In `class PPEStockBatch`, add after `location`:

```python
    supplier_id: Mapped[str | None] = mapped_column(
        ForeignKey("ppe_supplier.id", ondelete="SET NULL"), nullable=True, index=True
    )
    supplier: Mapped["PPESupplier | None"] = relationship("PPESupplier")
```

(No relationship on `PPEItem` — resolution reads the scalar `preferred_supplier_id` and batches supplier loads, so a lazy relationship would only invite N+1.)

- [ ] **Step 4: Re-export `PPESupplier` from `app.models.models` and `app.models.ppe_registry`**

`app.models.ppe.py` is imported by `models.py`; confirm `PPESupplier` is picked up by the `from app.models.ppe import *`-style re-export in `models.py` (grep `PPEStockBatch` in `models.py` and add `PPESupplier` beside it in the same import/`__all__`). Then add `PPESupplier` to the `from app.models.models import (...)` list and `__all__` in `backend/app/models/ppe_registry.py`.

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest backend/tests/test_ppe_supplier_model.py -q`
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/ppe.py backend/app/models/ppe_registry.py backend/app/models/models.py backend/tests/test_ppe_supplier_model.py
git commit -m "feat(p10-06): PPESupplier model + batch/item provenance FKs"
```

---

## Task 2: Migration `wa08`

**Files:**
- Create: `backend/app/migrations/versions/20260704_wa08_ppe_supplier.py`
- Test: `backend/tests/test_wa08_ppe_supplier_migration.py`

- [ ] **Step 1: Write the failing test** (mirror `test_wa07_*`, whitespace-insensitive)

```python
# backend/tests/test_wa08_ppe_supplier_migration.py
"""wa08 adds the ppe_supplier directory + batch/item provenance FKs (P10-06)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260704_wa08_ppe_supplier.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("wa08_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIGRATION.exists()


def test_migration_revision_metadata():
    mod = _load()
    assert mod.revision == "20260704_wa08_ppe_supplier"
    assert mod.down_revision == "20260704_wa07_ppe_stock_batch_location_unique"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade():
    mod = _load()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)


def test_migration_shape():
    nospace = "".join(_MIGRATION.read_text(encoding="utf-8").split())
    assert 'create_table("ppe_supplier"' in nospace
    assert '"uq_ppe_supplier_name"' in nospace
    assert 'add_column("ppe_stock_batch"' in nospace
    assert 'add_column("ppeitem"' in nospace
    assert '"supplier_id"' in nospace
    assert '"preferred_supplier_id"' in nospace
    assert 'ondelete="SETNULL"' in nospace  # "SET NULL" with spaces stripped
    assert 'drop_table("ppe_supplier")' in nospace
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest backend/tests/test_wa08_ppe_supplier_migration.py -q`
Expected: FAIL — migration file missing.

- [ ] **Step 3: Write the migration**

```python
# backend/app/migrations/versions/20260704_wa08_ppe_supplier.py
"""ppe supplier directory + batch/item provenance FKs (P10-06).

Additive: creates ppe_supplier (directory) + adds nullable supplier_id to
ppe_stock_batch (batch provenance) and preferred_supplier_id to ppeitem
(explicit reorder supplier). No data backfill, no enum. Chains off wa07.

Revision ID: 20260704_wa08_ppe_supplier
Revises: 20260704_wa07_ppe_stock_batch_location_unique
Create Date: 2026-07-04 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260704_wa08_ppe_supplier"
down_revision = "20260704_wa07_ppe_stock_batch_location_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppe_supplier",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("inn", sa.String(length=12), nullable=True),
        sa.Column("contact_email", sa.String(length=255), nullable=True),
        sa.Column("contact_phone", sa.String(length=64), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_ppe_supplier_name"),
    )
    op.create_index(op.f("ix_ppe_supplier_tenant_id"), "ppe_supplier", ["tenant_id"])

    op.add_column("ppe_stock_batch", sa.Column("supplier_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_ppe_stock_batch_supplier_id", "ppe_stock_batch", "ppe_supplier",
        ["supplier_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_ppe_stock_batch_supplier_id"), "ppe_stock_batch", ["supplier_id"])

    op.add_column("ppeitem", sa.Column("preferred_supplier_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_ppeitem_preferred_supplier_id", "ppeitem", "ppe_supplier",
        ["preferred_supplier_id"], ["id"], ondelete="SET NULL",
    )
    op.create_index(op.f("ix_ppeitem_preferred_supplier_id"), "ppeitem", ["preferred_supplier_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_ppeitem_preferred_supplier_id"), table_name="ppeitem")
    op.drop_constraint("fk_ppeitem_preferred_supplier_id", "ppeitem", type_="foreignkey")
    op.drop_column("ppeitem", "preferred_supplier_id")

    op.drop_index(op.f("ix_ppe_stock_batch_supplier_id"), table_name="ppe_stock_batch")
    op.drop_constraint("fk_ppe_stock_batch_supplier_id", "ppe_stock_batch", type_="foreignkey")
    op.drop_column("ppe_stock_batch", "supplier_id")

    op.drop_index(op.f("ix_ppe_supplier_tenant_id"), table_name="ppe_supplier")
    op.drop_table("ppe_supplier")
```

- [ ] **Step 4: Run black + the test, verify pass**

Run: `python -m black backend/app/migrations/versions/20260704_wa08_ppe_supplier.py` then
`python -m pytest backend/tests/test_wa08_ppe_supplier_migration.py -q`
Expected: PASS (4 passed). (Run black first so line-wrapping can't break substring asserts.)

- [ ] **Step 5: Verify single alembic head**

Run: `$env:PYTHONPATH="backend"; python -m alembic -c backend/app/migrations/alembic.ini heads`
Expected: single head `20260704_wa08_ppe_supplier`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/migrations/versions/20260704_wa08_ppe_supplier.py backend/tests/test_wa08_ppe_supplier_migration.py
git commit -m "feat(p10-06): wa08 migration — ppe_supplier + provenance FKs"
```

---

## Task 3: Supplier CRUD service

**Files:**
- Create: `backend/app/modules/ppe/suppliers.py`
- Test: `tests/api/test_ppe_suppliers_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ppe_suppliers_service.py
"""DB-level tests for the PPE supplier directory service (P10-06)."""

from __future__ import annotations

import pytest

from app.modules.ppe.suppliers import (
    SupplierNameConflict,
    SupplierNotFound,
    create_supplier,
    get_supplier,
    list_suppliers,
    soft_delete_supplier,
    update_supplier,
)
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_create_and_get(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = await create_supplier(session, tenant_id=tenant.id, name="Вендор", inn="7701234567")
        got = await get_supplier(session, tenant.id, sup.id)
        assert got.name == "Вендор"
        assert got.inn == "7701234567"


@pytest.mark.asyncio
async def test_duplicate_name_conflicts(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        await create_supplier(session, tenant_id=tenant.id, name="Дубль")
        with pytest.raises(SupplierNameConflict):
            await create_supplier(session, tenant_id=tenant.id, name="Дубль")


@pytest.mark.asyncio
async def test_list_excludes_soft_deleted_and_paginates(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        a = await create_supplier(session, tenant_id=tenant.id, name="A")
        await create_supplier(session, tenant_id=tenant.id, name="B")
        await soft_delete_supplier(session, tenant.id, a.id)
        items, total = await list_suppliers(session, tenant.id, limit=50, offset=0)
        assert total == 1
        assert [s.name for s in items] == ["B"]


@pytest.mark.asyncio
async def test_update_and_missing(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = await create_supplier(session, tenant_id=tenant.id, name="Old")
        updated = await update_supplier(session, tenant.id, sup.id, name="New", contact_phone="+7")
        assert updated.name == "New"
        assert updated.contact_phone == "+7"
        with pytest.raises(SupplierNotFound):
            await get_supplier(session, tenant.id, "nope")


@pytest.mark.asyncio
async def test_tenant_isolation(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        t1 = await data_factory.ensure_tenant(session=session)
        t2 = await data_factory.ensure_tenant(session=session, slug="other")
        sup = await create_supplier(session, tenant_id=t1.id, name="OnlyT1")
        with pytest.raises(SupplierNotFound):
            await get_supplier(session, t2.id, sup.id)
```

(If `ensure_tenant` has no `slug` kwarg, seed the second tenant however the sibling tests do — check `tests/utils/factories.py`.)

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/api/test_ppe_suppliers_service.py -q`
Expected: FAIL — module `app.modules.ppe.suppliers` missing.

- [ ] **Step 3: Write the service**

```python
# backend/app/modules/ppe/suppliers.py
"""PPE supplier directory CRUD (P10-06). Thin async service over PPESupplier.

Name is unique per tenant; a duplicate surfaces as SupplierNameConflict (mapped
to 409 by the route). Soft-delete sets deleted_at; lists exclude soft-deleted.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import PPESupplier


class SupplierNotFound(Exception):
    def __init__(self, supplier_id: str) -> None:
        super().__init__(f"PPE supplier not found: {supplier_id}")
        self.supplier_id = supplier_id


class SupplierNameConflict(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"PPE supplier name already exists: {name}")
        self.name = name


async def _load(session: AsyncSession, tenant_id: str, supplier_id: str) -> PPESupplier:
    stmt = select(PPESupplier).where(
        PPESupplier.id == supplier_id,
        PPESupplier.tenant_id == tenant_id,
        PPESupplier.deleted_at.is_(None),
    )
    sup = (await session.execute(stmt)).scalar_one_or_none()
    if sup is None:
        raise SupplierNotFound(supplier_id)
    return sup


async def create_supplier(
    session: AsyncSession, *, tenant_id: str, name: str,
    inn: str | None = None, contact_email: str | None = None, contact_phone: str | None = None,
) -> PPESupplier:
    sup = PPESupplier(
        tenant_id=tenant_id, name=name, inn=inn,
        contact_email=contact_email, contact_phone=contact_phone,
    )
    session.add(sup)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise SupplierNameConflict(name) from exc
    await session.refresh(sup)
    return sup


async def get_supplier(session: AsyncSession, tenant_id: str, supplier_id: str) -> PPESupplier:
    return await _load(session, tenant_id, supplier_id)


async def list_suppliers(
    session: AsyncSession, tenant_id: str, *, limit: int, offset: int
) -> tuple[list[PPESupplier], int]:
    base = (
        PPESupplier.tenant_id == tenant_id,
        PPESupplier.deleted_at.is_(None),
    )
    items = list(
        (
            await session.execute(
                select(PPESupplier).where(*base).order_by(PPESupplier.name.asc())
                .limit(limit).offset(offset)
            )
        ).scalars().all()
    )
    total = (await session.execute(select(func.count()).where(*base))).scalar_one()
    return items, int(total or 0)


async def update_supplier(
    session: AsyncSession, tenant_id: str, supplier_id: str, **fields
) -> PPESupplier:
    sup = await _load(session, tenant_id, supplier_id)
    for key, value in fields.items():
        setattr(sup, key, value)
    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise SupplierNameConflict(fields.get("name", sup.name)) from exc
    await session.refresh(sup)
    return sup


async def soft_delete_supplier(session: AsyncSession, tenant_id: str, supplier_id: str) -> None:
    sup = await _load(session, tenant_id, supplier_id)
    sup.deleted_at = datetime.now(tz=timezone.utc)
    await session.flush()
```

**Note on `session.rollback()` in the conflict path:** verify sibling PPE services handle `IntegrityError` this way inside the request transaction; if the route owns the transaction, prefer a pre-check `select` by `(tenant_id, name, deleted_at IS NULL)` returning `SupplierNameConflict` before `add`, to avoid rolling back the caller's unit of work. Pick whichever matches `routes/ppe.py` transaction ownership (the API test in Task 4 is the arbiter).

- [ ] **Step 4: Run tests, verify pass**

Run: `python -m pytest tests/api/test_ppe_suppliers_service.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/modules/ppe/suppliers.py tests/api/test_ppe_suppliers_service.py
git commit -m "feat(p10-06): supplier directory CRUD service"
```

---

## Task 4: Supplier schemas + CRUD API

**Files:**
- Modify: `backend/app/schemas/ppe.py`, `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_suppliers_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ppe_suppliers_api.py
"""API contract for the PPE supplier directory (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.feature import Feature, FeatureEnablement
from app.models.models import RoleEnum
from tests.utils.factories import TestDataFactory


async def _set_warehouse_flag(sessionmaker, data_factory, *, on: bool):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        from sqlalchemy import select
        feature = (
            await session.execute(select(Feature).where(Feature.code == "warehouse"))
        ).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=on))
        await session.commit()


@pytest.mark.asyncio
async def test_supplier_crud_roundtrip(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    created = await async_client.post(
        "/api/v1/ppe/suppliers",
        json={"name": "Вендор", "inn": "7701234567", "contact_email": "s@ex.com"},
        headers=headers,
    )
    assert created.status_code == status.HTTP_201_CREATED, created.text
    sid = created.json()["id"]

    listed = await async_client.get("/api/v1/ppe/suppliers", headers=headers)
    assert listed.status_code == status.HTTP_200_OK
    assert any(s["id"] == sid for s in listed.json()["items"])

    patched = await async_client.patch(
        f"/api/v1/ppe/suppliers/{sid}", json={"name": "Вендор-2"}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK
    assert patched.json()["name"] == "Вендор-2"

    deleted = await async_client.delete(f"/api/v1/ppe/suppliers/{sid}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"/api/v1/ppe/suppliers/{sid}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post("/api/v1/ppe/suppliers", json={"name": "Dup"}, headers=headers)
    dup = await async_client.post("/api/v1/ppe/suppliers", json={"name": "Dup"}, headers=headers)
    assert dup.status_code == status.HTTP_409_CONFLICT, dup.text


@pytest.mark.asyncio
async def test_suppliers_404_when_feature_disabled(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    await _set_warehouse_flag(sessionmaker, data_factory, on=False)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    listed = await async_client.get("/api/v1/ppe/suppliers", headers=headers)
    assert listed.status_code == status.HTTP_404_NOT_FOUND
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/api/test_ppe_suppliers_api.py -q`
Expected: FAIL — `/api/v1/ppe/suppliers` 404 (route absent).

- [ ] **Step 3: Add schemas** (in `backend/app/schemas/ppe.py`, after `PPEItemPage`)

```python
class PPESupplierCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)


class PPESupplierUpdate(BaseSchema):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    inn: str | None = Field(default=None, max_length=12)
    contact_email: str | None = Field(default=None, max_length=255)
    contact_phone: str | None = Field(default=None, max_length=64)


class PPESupplierRead(BaseSchema):
    id: str
    name: str
    inn: str | None
    contact_email: str | None
    contact_phone: str | None


class PPESupplierPage(BaseSchema):
    items: list[PPESupplierRead]
    total: int
```

- [ ] **Step 4: Add the conflict helper + routes** (in `backend/app/api/routes/ppe.py`)

Add near `_ppe_conflict`:

```python
def _ppe_supplier_conflict(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=api_problem_detail(
            code="PPE_SUPPLIER_CONFLICT", message=message, error_type="ppe"
        ),
    )
```

Import the service + schemas at the top of the file:

```python
from app.modules.ppe.suppliers import (
    SupplierNameConflict, SupplierNotFound,
    create_supplier, get_supplier, list_suppliers, soft_delete_supplier, update_supplier,
)
from app.schemas.ppe import PPESupplierCreate, PPESupplierPage, PPESupplierRead, PPESupplierUpdate
```

Add the five routes (mirror `/items`, all behind `WarehouseFeatureGate`). Place beside the other supplier/stock routes:

```python
@router.post(
    "/suppliers", response_model=PPESupplierRead,
    status_code=status.HTTP_201_CREATED, dependencies=[WarehouseFeatureGate],
)
@audit_operation("create", "ppe_supplier")
async def create_supplier_endpoint(
    payload: PPESupplierCreate, tenant: TenantDep, session: SessionDep, access: EditorAccess,
) -> PPESupplierRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        sup = await create_supplier(
            session, tenant_id=tenant.id, name=payload.name, inn=payload.inn,
            contact_email=payload.contact_email, contact_phone=payload.contact_phone,
        )
    except SupplierNameConflict as exc:
        raise _ppe_supplier_conflict(str(exc)) from exc
    return PPESupplierRead.model_validate(sup)


@router.get("/suppliers", response_model=PPESupplierPage, dependencies=[WarehouseFeatureGate])
async def list_suppliers_endpoint(
    request: Request, response: Response, tenant: TenantDep, session: SessionDep,
    access: ManagerAccess, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
) -> PPESupplierPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    items, total = await list_suppliers(session, tenant.id, limit=limit, offset=offset)
    etag = compute_list_etag(
        tenant_id=str(tenant.id), items=items,
        scalars=[("total", total), ("limit", limit), ("offset", offset)],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=build_not_modified_headers(etag))
    return PPESupplierPage(items=[PPESupplierRead.model_validate(s) for s in items], total=total)


@router.get("/suppliers/{supplier_id}", response_model=PPESupplierRead, dependencies=[WarehouseFeatureGate])
async def get_supplier_endpoint(
    supplier_id: str, tenant: TenantDep, session: SessionDep, access: ManagerAccess,
) -> PPESupplierRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        sup = await get_supplier(session, tenant.id, supplier_id)
    except SupplierNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE supplier not found") from exc
    return PPESupplierRead.model_validate(sup)


@router.patch("/suppliers/{supplier_id}", response_model=PPESupplierRead, dependencies=[WarehouseFeatureGate])
@audit_operation("update", "ppe_supplier")
async def update_supplier_endpoint(
    supplier_id: str, payload: PPESupplierUpdate, tenant: TenantDep, session: SessionDep, access: EditorAccess,
) -> PPESupplierRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        sup = await update_supplier(
            session, tenant.id, supplier_id, **payload.model_dump(exclude_unset=True)
        )
    except SupplierNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE supplier not found") from exc
    except SupplierNameConflict as exc:
        raise _ppe_supplier_conflict(str(exc)) from exc
    return PPESupplierRead.model_validate(sup)


@router.delete(
    "/suppliers/{supplier_id}", status_code=status.HTTP_204_NO_CONTENT,
    response_model=None, dependencies=[WarehouseFeatureGate],
)
@audit_operation("delete", "ppe_supplier")
async def delete_supplier_endpoint(
    supplier_id: str, tenant: TenantDep, session: SessionDep, access: EditorAccess,
) -> None:
    TenantContextValidator.ensure_tenant_context(tenant)
    try:
        await soft_delete_supplier(session, tenant.id, supplier_id)
    except SupplierNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "PPE supplier not found") from exc
```

**Route order caveat:** define `/suppliers` routes **before** any `/{...}`-catch-all is registered; there is none conflicting, but keep `/suppliers/{supplier_id}` after the collection routes. Also confirm `PPESupplierRead.model_validate(sup)` works with `BaseSchema` ORM mode (sibling reads use `model_validate` on ORM rows — `_item_schema`).

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/api/test_ppe_suppliers_api.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/api/test_ppe_suppliers_api.py
git commit -m "feat(p10-06): supplier directory CRUD API"
```

---

## Task 5: Batch provenance (`supplier_id`) + transfer copy

**Files:**
- Modify: `backend/app/schemas/ppe.py`, `backend/app/api/routes/ppe.py`, `backend/app/modules/ppe/stock.py`
- Test: `tests/api/test_ppe_supplier_provenance.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ppe_supplier_provenance.py
"""Batch supplier provenance + transfer copies supplier (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select

from app.models.models import RoleEnum
from app.models.ppe_registry import PPEStockBatch
from app.modules.ppe.stock import transfer_stock
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


async def _supplier(async_client, headers, name="Вендор") -> str:
    r = await async_client.post("/api/v1/ppe/suppliers", json={"name": name}, headers=headers)
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


async def _item(async_client, headers, name="Каска") -> str:
    r = await async_client.post(
        "/api/v1/ppe/items", json={"name": name, "category": PPEItemCategory.HEAD.value}, headers=headers
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_batch_create_stores_and_returns_supplier(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    sid = await _supplier(async_client, headers)
    item_id = await _item(async_client, headers)

    r = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B-1", "quantity": 10, "location": "A", "supplier_id": sid},
        headers=headers,
    )
    assert r.status_code == status.HTTP_201_CREATED, r.text
    assert r.json()["supplier_id"] == sid


@pytest.mark.asyncio
async def test_batch_create_unknown_supplier_400(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    item_id = await _item(async_client, headers)
    r = await async_client.post(
        "/api/v1/ppe/stock/batches",
        json={"item_id": item_id, "batch_no": "B-1", "quantity": 1, "supplier_id": "nope"},
        headers=headers,
    )
    assert r.status_code in (status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND), r.text


@pytest.mark.asyncio
async def test_transfer_copies_supplier_to_dest_batch(sessionmaker, data_factory: TestDataFactory):
    from app.models.models import PPEItem, PPESupplier

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        sup = PPESupplier(tenant_id=tenant.id, name="Вендор")
        session.add(sup)
        await session.flush()
        item = PPEItem(tenant_id=tenant.id, name="Каска")
        session.add(item)
        await session.flush()
        source = PPEStockBatch(
            tenant_id=tenant.id, item_id=item.id, batch_no="B-1",
            quantity=10, location="A", supplier_id=sup.id,
        )
        session.add(source)
        await session.flush()

        result = await transfer_stock(
            session, tenant_id=tenant.id, source_batch_id=source.id, to_location="B", quantity=4
        )
        dest = (
            await session.execute(select(PPEStockBatch).where(PPEStockBatch.id == result.dest_batch_id))
        ).scalar_one()
        assert dest.supplier_id == sup.id  # provenance copied
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/api/test_ppe_supplier_provenance.py -q`
Expected: FAIL — `supplier_id` unknown field / not copied.

- [ ] **Step 3: Extend batch schemas** (in `backend/app/schemas/ppe.py`)

Add `supplier_id: str | None = None` to `PPEStockBatchCreate` and `PPEStockBatchUpdate`; add `supplier_id: str | None` to `PPEStockBatchRead` (after `location`).

- [ ] **Step 4: Copy supplier in transfer** (in `backend/app/modules/ppe/stock.py`, `_find_or_create_dest_batch`)

In the `PPEStockBatch(...)` construction inside `_find_or_create_dest_batch`, add `supplier_id=source.supplier_id` alongside the existing provenance fields:

```python
    dest = PPEStockBatch(
        tenant_id=tenant_id,
        item_id=source.item_id,
        batch_no=source.batch_no,
        quantity=0,
        location=to_location,
        received_at=source.received_at,
        certificate_no=source.certificate_no,
        certificate_expires_at=source.certificate_expires_at,
        supplier_id=source.supplier_id,
    )
```

- [ ] **Step 5: Wire batch create/update route** (in `backend/app/api/routes/ppe.py`, `create_stock_batch`/`update_stock_batch`)

In `create_stock_batch`: after loading the item (item existence already validated), if `payload.supplier_id` is set, validate the supplier exists for the tenant (reuse `get_supplier`, map `SupplierNotFound` → `_ppe_bad_request("unknown supplier")`), then pass `supplier_id=payload.supplier_id` into the `PPEStockBatch(...)` constructor. In `update_stock_batch`: include `supplier_id` in the `model_dump(exclude_unset=True)` set-loop (validate the same way when present and non-None). Ensure `PPEStockBatchRead` is built so it includes `supplier_id` (it uses `model_validate`/explicit fields — add the field).

- [ ] **Step 6: Run tests, verify pass**

Run: `python -m pytest tests/api/test_ppe_supplier_provenance.py tests/api/test_ppe_stock_transfers_service.py -q`
Expected: PASS (transfer regression stays green; the invariant `before==after` test in `test_ppe_stock_transfers_service.py` still passes — supplier is metadata).

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/ppe.py backend/app/api/routes/ppe.py backend/app/modules/ppe/stock.py tests/api/test_ppe_supplier_provenance.py
git commit -m "feat(p10-06): batch supplier provenance + transfer copy"
```

---

## Task 6: Item `preferred_supplier_id` wiring

**Files:**
- Modify: `backend/app/schemas/ppe.py`, `backend/app/api/routes/ppe.py`
- Test: extend `tests/api/test_ppe_supplier_provenance.py`

- [ ] **Step 1: Add the failing test** (append to `test_ppe_supplier_provenance.py`)

```python
@pytest.mark.asyncio
async def test_item_preferred_supplier_roundtrip(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    sid = await _supplier(async_client, headers)
    item_id = await _item(async_client, headers)

    patched = await async_client.patch(
        f"/api/v1/ppe/items/{item_id}", json={"preferred_supplier_id": sid}, headers=headers
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["preferred_supplier_id"] == sid
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/api/test_ppe_supplier_provenance.py::test_item_preferred_supplier_roundtrip -q`
Expected: FAIL — `preferred_supplier_id` not accepted/returned.

- [ ] **Step 3: Extend item schemas** (in `backend/app/schemas/ppe.py`)

Add `preferred_supplier_id: str | None = None` to `PPEItemCreate` and `PPEItemUpdate`; add `preferred_supplier_id: str | None` to `PPEItemRead`.

- [ ] **Step 4: Wire item create/update route** (in `backend/app/api/routes/ppe.py`)

In `create_item`, pass `preferred_supplier_id=payload.preferred_supplier_id` into the `PPEItem(...)` constructor; validate it exists (when set) via `get_supplier` → `_ppe_bad_request` on `SupplierNotFound`. In `update_item`, `preferred_supplier_id` flows through the existing `model_dump(exclude_unset=True)` set-loop; add the same validation when present and non-None. `_item_schema` uses `PPEItemRead.model_validate(item)` so the new field is returned automatically.

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/api/test_ppe_supplier_provenance.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/api/test_ppe_supplier_provenance.py
git commit -m "feat(p10-06): item preferred_supplier_id wiring"
```

---

## Task 7: Supplier resolution in `compute_shortages` + shortage fields

**Files:**
- Modify: `backend/app/modules/ppe/stock.py`, `backend/app/schemas/ppe.py`, `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_reorder_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_ppe_reorder_service.py
"""Supplier resolution (explicit -> history) + reorder draft (P10-06)."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from app.models.models import PPEItem, PPESupplier
from app.models.ppe_registry import PPEStockBatch
from app.modules.ppe.stock import compute_shortages
from tests.utils.factories import TestDataFactory

NOW = datetime(2026, 7, 4, tzinfo=timezone.utc)


async def _item(session, tenant_id, *, name, min_stock, preferred=None):
    it = PPEItem(tenant_id=tenant_id, name=name, min_stock=min_stock, preferred_supplier_id=preferred)
    session.add(it)
    await session.flush()
    return it


async def _batch(session, tenant_id, item_id, *, qty, supplier_id=None, received=None, no="B"):
    b = PPEStockBatch(
        tenant_id=tenant_id, item_id=item_id, batch_no=no, quantity=qty,
        location="A", supplier_id=supplier_id, received_at=received,
    )
    session.add(b)
    await session.flush()
    return b


@pytest.mark.asyncio
async def test_explicit_supplier_wins(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        exp = PPESupplier(tenant_id=tenant.id, name="Explicit")
        hist = PPESupplier(tenant_id=tenant.id, name="History")
        session.add_all([exp, hist])
        await session.flush()
        item = await _item(session, tenant.id, name="Каска", min_stock=10, preferred=exp.id)
        await _batch(session, tenant.id, item.id, qty=1, supplier_id=hist.id, received=date(2026, 6, 1))

        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id == exp.id
        assert row.supplier_name == "Explicit"
        assert row.supplier_source == "explicit"


@pytest.mark.asyncio
async def test_history_fallback_picks_latest(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        old = PPESupplier(tenant_id=tenant.id, name="Old")
        new = PPESupplier(tenant_id=tenant.id, name="New")
        session.add_all([old, new])
        await session.flush()
        item = await _item(session, tenant.id, name="Каска", min_stock=10)  # no preferred
        await _batch(session, tenant.id, item.id, qty=1, supplier_id=old.id, received=date(2026, 1, 1), no="OLD")
        await _batch(session, tenant.id, item.id, qty=1, supplier_id=new.id, received=date(2026, 6, 1), no="NEW")

        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id == new.id
        assert row.supplier_source == "history"


@pytest.mark.asyncio
async def test_no_supplier_when_none(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        item = await _item(session, tenant.id, name="Каска", min_stock=10)
        await _batch(session, tenant.id, item.id, qty=1)  # no supplier
        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id is None
        assert row.supplier_source is None


@pytest.mark.asyncio
async def test_soft_deleted_resolved_supplier_is_none(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        dead = PPESupplier(tenant_id=tenant.id, name="Dead", deleted_at=NOW)
        session.add(dead)
        await session.flush()
        item = await _item(session, tenant.id, name="Каска", min_stock=10, preferred=dead.id)
        await _batch(session, tenant.id, item.id, qty=1)
        rows = await compute_shortages(session, tenant.id, now=NOW)
        row = next(r for r in rows if r.item_id == item.id)
        assert row.supplier_id is None
        assert row.supplier_source is None
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/api/test_ppe_reorder_service.py -q`
Expected: FAIL — `ShortageRow` has no `supplier_*` attributes.

- [ ] **Step 3: Extend `ShortageRow` + add resolution to `compute_shortages`** (in `backend/app/modules/ppe/stock.py`)

Add fields to the `ShortageRow` dataclass:

```python
    supplier_id: str | None = None
    supplier_name: str | None = None
    supplier_inn: str | None = None
    supplier_contact: str | None = None
    supplier_source: str | None = None
```

Add a resolver helper (module-level, in `stock.py`), imported `PPESupplier` at top (`from app.models.models import PPESupplier` — extend the existing import line):

```python
async def _resolve_item_suppliers(
    session: AsyncSession, tenant_id: str, items: list[PPEItem]
) -> dict[str, tuple[PPESupplier, str]]:
    """Map item_id -> (supplier, source) where source is 'explicit'|'history'.

    Explicit ``item.preferred_supplier_id`` wins; otherwise the most recently
    received batch supplier (received_at desc nulls-last, created_at desc). Only
    non-deleted suppliers count; unresolved items are simply absent from the map.
    """
    item_ids = [i.id for i in items]
    if not item_ids:
        return {}

    source_for_item: dict[str, str] = {}
    wanted: dict[str, str] = {}  # item_id -> supplier_id

    for it in items:
        if it.preferred_supplier_id:
            wanted[it.id] = it.preferred_supplier_id
            source_for_item[it.id] = "explicit"

    remaining = [iid for iid in item_ids if iid not in wanted]
    if remaining:
        batch_rows = (
            await session.execute(
                select(
                    PPEStockBatch.item_id, PPEStockBatch.supplier_id,
                    PPEStockBatch.received_at, PPEStockBatch.created_at,
                ).where(
                    PPEStockBatch.tenant_id == tenant_id,
                    PPEStockBatch.item_id.in_(remaining),
                    PPEStockBatch.supplier_id.is_not(None),
                    PPEStockBatch.deleted_at.is_(None),
                )
            )
        ).all()
        # latest per item: received_at desc (None last), created_at desc
        best: dict[str, tuple] = {}
        for iid, sid, received, created in batch_rows:
            key = (received is not None, received or date.min, created)
            if iid not in best or key > best[iid][0]:
                best[iid] = (key, sid)
        for iid, (_key, sid) in best.items():
            wanted[iid] = sid
            source_for_item[iid] = "history"

    if not wanted:
        return {}
    suppliers = {
        s.id: s
        for s in (
            await session.execute(
                select(PPESupplier).where(
                    PPESupplier.tenant_id == tenant_id,
                    PPESupplier.id.in_(set(wanted.values())),
                    PPESupplier.deleted_at.is_(None),
                )
            )
        ).scalars().all()
    }
    resolved: dict[str, tuple[PPESupplier, str]] = {}
    for iid, sid in wanted.items():
        sup = suppliers.get(sid)
        if sup is not None:  # soft-deleted / missing -> unresolved
            resolved[iid] = (sup, source_for_item[iid])
    return resolved
```

In `compute_shortages`, after building `items` and before the row loop, call `resolved = await _resolve_item_suppliers(session, tenant_id, items)`; when constructing each `ShortageRow`, populate the supplier fields:

```python
        sup_tuple = resolved.get(item.id)
        supplier = sup_tuple[0] if sup_tuple else None
        rows.append(
            ShortageRow(
                ...,
                supplier_id=supplier.id if supplier else None,
                supplier_name=supplier.name if supplier else None,
                supplier_inn=supplier.inn if supplier else None,
                supplier_contact=(supplier.contact_email or supplier.contact_phone) if supplier else None,
                supplier_source=sup_tuple[1] if sup_tuple else None,
            )
        )
```

Ensure `date` is imported in `stock.py` (it already imports `from datetime import date, datetime, timedelta, timezone`).

- [ ] **Step 4: Extend shortage schema + route** (in `backend/app/schemas/ppe.py` + `routes/ppe.py`)

Add to `PPEStockShortageRead`: `supplier_id / supplier_name / supplier_inn / supplier_contact / supplier_source` (all `str | None`). In `list_stock_shortages` route, pass them from `r` into `PPEStockShortageRead(...)`.

- [ ] **Step 5: Run tests, verify pass**

Run: `python -m pytest tests/api/test_ppe_reorder_service.py tests/api/test_ppe_shortage_service.py -q`
Expected: PASS (resolution tests + existing shortage service regression green).

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/ppe/stock.py backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/api/test_ppe_reorder_service.py
git commit -m "feat(p10-06): resolve reorder supplier (explicit->history) in shortages"
```

---

## Task 8: Reorder draft + `GET /stock/reorder`

**Files:**
- Modify: `backend/app/modules/ppe/stock.py`, `backend/app/schemas/ppe.py`, `backend/app/api/routes/ppe.py`
- Test: `tests/api/test_ppe_reorder_api.py` + extend `test_ppe_reorder_service.py`

- [ ] **Step 1: Write the failing test** (`build_reorder_draft` unit + API)

Append to `tests/api/test_ppe_reorder_service.py`:

```python
from app.modules.ppe.stock import ShortageRow, build_reorder_draft


def _row(item_id, deficit, below, sid, sname):
    return ShortageRow(
        item_id=item_id, item_name=item_id, min_stock=10, on_hand=0, deficit=deficit,
        below_threshold=below, avg_daily_consumption=0.0, days_to_depletion=None,
        projected_breach_date=None, supplier_id=sid, supplier_name=sname,
        supplier_inn=None, supplier_contact=None, supplier_source="explicit" if sid else None,
    )


def test_build_reorder_draft_groups_by_supplier():
    rows = [
        _row("i1", 5, True, "s1", "Alpha"),
        _row("i2", 3, True, "s1", "Alpha"),
        _row("i3", 2, True, None, None),      # unassigned
        _row("i4", 9, False, "s1", "Alpha"),  # not below-threshold -> excluded
    ]
    draft = build_reorder_draft(rows)
    by_supplier = {g.supplier_id: g for g in draft.groups}
    assert by_supplier["s1"].line_count == 2
    assert by_supplier["s1"].total_deficit == 8
    assert by_supplier[None].line_count == 1          # unassigned group present
    assert draft.groups[-1].supplier_id is None        # unassigned sorts last
    assert draft.total_lines == 3
    assert draft.total_deficit == 10
```

Create `tests/api/test_ppe_reorder_api.py`:

```python
# tests/api/test_ppe_reorder_api.py
"""API contract for /stock/reorder + shortage supplier fields (P10-06)."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.schemas.ppe import PPEItemCategory
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_reorder_groups_below_threshold_by_supplier(async_client: AsyncClient, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        await data_factory.ensure_tenant(session=session)
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)

    sup = await async_client.post("/api/v1/ppe/suppliers", json={"name": "Alpha"}, headers=headers)
    sid = sup.json()["id"]
    item = await async_client.post(
        "/api/v1/ppe/items",
        json={"name": "Каска", "category": PPEItemCategory.HEAD.value,
              "min_stock": 10, "preferred_supplier_id": sid},
        headers=headers,
    )
    item_id = item.json()["id"]
    # on_hand 0 < min_stock 10 -> below threshold, deficit 10

    resp = await async_client.get("/api/v1/ppe/stock/reorder", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    grp = next(g for g in body["groups"] if g["supplier_id"] == sid)
    assert grp["supplier_name"] == "Alpha"
    line = next(ln for ln in grp["lines"] if ln["item_id"] == item_id)
    assert line["deficit"] == 10


@pytest.mark.asyncio
async def test_reorder_404_when_feature_disabled(async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory):
    from app.models.feature import Feature, FeatureEnablement
    from sqlalchemy import select

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        feature = (await session.execute(select(Feature).where(Feature.code == "warehouse"))).scalar_one_or_none()
        if feature is None:
            feature = Feature(code="warehouse", title="Warehouse")
            session.add(feature)
            await session.flush()
        session.add(FeatureEnablement(tenant_id=tenant.id, feature_id=feature.id, on=False))
        await session.commit()
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.get("/api/v1/ppe/stock/reorder", headers=headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND
```

- [ ] **Step 2: Run it, verify it fails**

Run: `python -m pytest tests/api/test_ppe_reorder_api.py "tests/api/test_ppe_reorder_service.py::test_build_reorder_draft_groups_by_supplier" -q`
Expected: FAIL — `build_reorder_draft` / `/stock/reorder` missing.

- [ ] **Step 3: Add reorder dataclasses + `build_reorder_draft`** (in `backend/app/modules/ppe/stock.py`)

```python
@dataclass(slots=True, frozen=True)
class ReorderLine:
    item_id: str
    item_name: str
    deficit: int


@dataclass(slots=True, frozen=True)
class ReorderGroup:
    supplier_id: str | None
    supplier_name: str | None
    supplier_inn: str | None
    supplier_contact: str | None
    lines: list[ReorderLine]
    line_count: int
    total_deficit: int


@dataclass(slots=True, frozen=True)
class ReorderDraft:
    groups: list[ReorderGroup]
    total_lines: int
    total_deficit: int


def build_reorder_draft(rows: list[ShortageRow]) -> ReorderDraft:
    """Group below-threshold shortage rows by resolved supplier. Rows with no
    supplier fall into a single ``supplier_id=None`` group that always sorts last."""
    buckets: dict[str | None, list[ShortageRow]] = {}
    for r in rows:
        if not (r.below_threshold and r.deficit > 0):
            continue
        buckets.setdefault(r.supplier_id, []).append(r)

    groups: list[ReorderGroup] = []
    for sid, rs in buckets.items():
        lines = [ReorderLine(item_id=r.item_id, item_name=r.item_name, deficit=r.deficit) for r in rs]
        head = rs[0]
        groups.append(
            ReorderGroup(
                supplier_id=sid,
                supplier_name=head.supplier_name if sid else None,
                supplier_inn=head.supplier_inn if sid else None,
                supplier_contact=head.supplier_contact if sid else None,
                lines=lines,
                line_count=len(lines),
                total_deficit=sum(ln.deficit for ln in lines),
            )
        )
    # named suppliers by name asc, unassigned (None) last
    groups.sort(key=lambda g: (g.supplier_id is None, (g.supplier_name or "").lower()))
    return ReorderDraft(
        groups=groups,
        total_lines=sum(g.line_count for g in groups),
        total_deficit=sum(g.total_deficit for g in groups),
    )
```

- [ ] **Step 4: Add reorder schemas** (in `backend/app/schemas/ppe.py`)

```python
class PPEReorderLineRead(BaseSchema):
    item_id: str
    item_name: str
    deficit: int


class PPEReorderGroupRead(BaseSchema):
    supplier_id: str | None
    supplier_name: str | None
    supplier_inn: str | None
    supplier_contact: str | None
    lines: list[PPEReorderLineRead]
    line_count: int
    total_deficit: int


class PPEReorderDraftRead(BaseSchema):
    groups: list[PPEReorderGroupRead]
    total_lines: int
    total_deficit: int
```

- [ ] **Step 5: Add the route** (in `backend/app/api/routes/ppe.py`)

```python
@router.get("/stock/reorder", response_model=PPEReorderDraftRead, dependencies=[WarehouseFeatureGate])
async def get_reorder_draft(
    tenant: TenantDep, session: SessionDep, access: ManagerAccess,
    window_days: int = Query(90, ge=1, le=365),
) -> PPEReorderDraftRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    rows = await compute_shortages(
        session, tenant.id, now=datetime.now(tz=timezone.utc),
        window_days=window_days, only_below=True,
    )
    draft = build_reorder_draft(rows)
    return PPEReorderDraftRead(
        groups=[
            PPEReorderGroupRead(
                supplier_id=g.supplier_id, supplier_name=g.supplier_name,
                supplier_inn=g.supplier_inn, supplier_contact=g.supplier_contact,
                lines=[PPEReorderLineRead(item_id=ln.item_id, item_name=ln.item_name, deficit=ln.deficit) for ln in g.lines],
                line_count=g.line_count, total_deficit=g.total_deficit,
            )
            for g in draft.groups
        ],
        total_lines=draft.total_lines, total_deficit=draft.total_deficit,
    )
```

Import `build_reorder_draft` (and the reorder schemas) at the top. Register the route beside `/stock/shortages`.

- [ ] **Step 6: Run tests, verify pass**

Run: `python -m pytest tests/api/test_ppe_reorder_api.py tests/api/test_ppe_reorder_service.py -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/modules/ppe/stock.py backend/app/schemas/ppe.py backend/app/api/routes/ppe.py tests/api/test_ppe_reorder_api.py tests/api/test_ppe_reorder_service.py
git commit -m "feat(p10-06): reorder draft grouped by supplier (GET /stock/reorder)"
```

---

## Task 9: Frontend API client (`warehouse.ts`)

**Files:**
- Modify: `frontend/src/api/warehouse.ts`

- [ ] **Step 1: Add DTOs + methods**

Extend `StockBatchDto` with `supplier_id?: string | null;`. Extend `PPEStockShortageDto` with `supplier_id`, `supplier_name`, `supplier_inn`, `supplier_contact` (all `string | null`) and `supplier_source: "explicit" | "history" | null`. Extend `CreateMovementInput`/batch-create inputs if a batch-create input type exists (add `supplier_id?`). Add:

```typescript
export type SupplierDto = {
  id: string;
  name: string;
  inn?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
};

export type SupplierInput = {
  name: string;
  inn?: string | null;
  contact_email?: string | null;
  contact_phone?: string | null;
};

export type ReorderLineDto = { item_id: string; item_name: string; deficit: number };
export type ReorderGroupDto = {
  supplier_id: string | null;
  supplier_name: string | null;
  supplier_inn: string | null;
  supplier_contact: string | null;
  lines: ReorderLineDto[];
  line_count: number;
  total_deficit: number;
};
export type ReorderDraftDto = {
  groups: ReorderGroupDto[];
  total_lines: number;
  total_deficit: number;
};
```

Add to the `warehouseApi` object:

```typescript
  async listSuppliers(): Promise<SupplierDto[]> {
    const response = await apiClient.get<PageResponse<SupplierDto>>("/ppe/suppliers", {
      params: { limit: 200, offset: 0 }
    });
    return response.data.items ?? [];
  },
  async createSupplier(input: SupplierInput): Promise<SupplierDto> {
    const response = await apiClient.post<SupplierDto>("/ppe/suppliers", input);
    return response.data;
  },
  async updateSupplier(id: string, input: Partial<SupplierInput>): Promise<SupplierDto> {
    const response = await apiClient.patch<SupplierDto>(`/ppe/suppliers/${id}`, input);
    return response.data;
  },
  async deleteSupplier(id: string): Promise<void> {
    await apiClient.delete(`/ppe/suppliers/${id}`);
  },
  async getReorderDraft(params?: { window_days?: number }): Promise<ReorderDraftDto> {
    const response = await apiClient.get<ReorderDraftDto>("/ppe/stock/reorder", { params });
    return response.data;
  },
```

If items are set via a separate items API module, add an `updatePreferredSupplier(itemId, supplierId)` there (or reuse the existing item PATCH); otherwise add a thin `patchItemPreferredSupplier` to `warehouseApi` calling `PATCH /ppe/items/{id}` with `{ preferred_supplier_id }`.

- [ ] **Step 2: Typecheck**

Run: `npm --prefix frontend run typecheck`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/warehouse.ts
git commit -m "feat(p10-06): warehouse API client — suppliers + reorder DTOs"
```

---

## Task 10: Frontend `WarehousePage` sections + vitest

**Files:**
- Modify: `frontend/src/pages/warehouse/WarehousePage.tsx`, `frontend/src/__tests__/WarehousePage.test.tsx`

- [ ] **Step 1: Write the failing vitest** (mirror existing WarehousePage tests — mock `warehouseApi`)

Add a test that mounts `WarehousePage`, mocks `warehouseApi.listSuppliers` to return one supplier and `getReorderDraft` to return one group, and asserts: (a) the «Поставщики» section renders the supplier name; (b) creating a supplier calls `warehouseApi.createSupplier`; (c) the «Дозаказ» view renders the supplier group and a line deficit; (d) the «Дефицит» rows render a supplier column. Follow the exact mocking/render pattern already in `WarehousePage.test.tsx` (it already mocks `warehouseApi` for movements/transfers/inventory). Example shape:

```typescript
it("renders suppliers section and creates a supplier", async () => {
  vi.mocked(warehouseApi.listSuppliers).mockResolvedValue([
    { id: "s1", name: "Alpha", inn: "7701234567", contact_email: null, contact_phone: null },
  ]);
  vi.mocked(warehouseApi.createSupplier).mockResolvedValue({
    id: "s2", name: "Beta", inn: null, contact_email: null, contact_phone: null,
  });
  render(<WarehousePage />);
  expect(await screen.findByText("Alpha")).toBeInTheDocument();
  // ...fill the supplier name input + submit, assert createSupplier called
});

it("renders reorder draft grouped by supplier", async () => {
  vi.mocked(warehouseApi.getReorderDraft).mockResolvedValue({
    groups: [{
      supplier_id: "s1", supplier_name: "Alpha", supplier_inn: null, supplier_contact: null,
      lines: [{ item_id: "i1", item_name: "Каска", deficit: 10 }], line_count: 1, total_deficit: 10,
    }],
    total_lines: 1, total_deficit: 10,
  });
  render(<WarehousePage />);
  expect(await screen.findByText(/Каска/)).toBeInTheDocument();
});
```

Add `listSuppliers`/`createSupplier`/`updateSupplier`/`deleteSupplier`/`getReorderDraft` to whatever `vi.mock("@/api/warehouse", ...)` factory the test file already declares (so the new methods are mockable).

- [ ] **Step 2: Run it, verify it fails**

Run: `npm --prefix frontend run test -- WarehousePage`
Expected: FAIL — sections not rendered / methods undefined.

- [ ] **Step 3: Implement the UI sections**

In `WarehousePage.tsx` (follow the existing section pattern — each stock area is a card with its own state + `useEffect` load):
1. **«Поставщики»** — load `listSuppliers` into state; render a list (name · ИНН · контакт) + a create/edit form (name required, inn, email, phone) + a delete button per row (calls `deleteSupplier`, reloads). Errors → the shared error banner.
2. **Batch/receipt form** — add a supplier `<select>` populated from suppliers state (blank option = none); include `supplier_id` in the batch-create payload.
3. **«Дефицит / мин-остаток»** — add a "Поставщик" column showing `supplier_name` + a small badge from `supplier_source` (`явный`/`история`); add an inline `<select>` per row that PATCHes `preferred_supplier_id` (via the item PATCH) and reloads shortages.
4. **«Дозаказ»** — load `getReorderDraft`; render one card per group (supplier name + contact + a table of {item_name, deficit} + `total_deficit`); the `supplier_id === null` group titled «Без поставщика»; a «Копировать»/CSV button that serializes the draft to clipboard/CSV client-side.

Keep to the page's existing styling utilities and table components.

- [ ] **Step 4: Run vitest + typecheck + build**

Run: `npm --prefix frontend run test -- WarehousePage` then `npm --prefix frontend run typecheck` then `npm --prefix frontend run build`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/warehouse/WarehousePage.tsx frontend/src/__tests__/WarehousePage.test.tsx
git commit -m "feat(p10-06): WarehousePage suppliers + reorder sections"
```

---

## Task 11: Regression gates + docs + OpenAPI baseline

**Files:**
- Modify: `docs/stabilization/openapi_routes_baseline.json`, `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md`, `CHANGELOG.md`, `AI_IMPLEMENTATION_REPORT.md`

- [ ] **Step 1: Lint the backend diff**

Run: `python -m ruff check backend/app tests` and `python -m black --check backend/app tests`
Fix any findings (run `python -m black backend/app tests` to auto-format), re-run ruff.

- [ ] **Step 2: Run the PPE regression slice**

Run (single invocation, 600000 ms):
`python -m pytest tests/api/test_ppe_supplier_model.py backend/tests/test_wa08_ppe_supplier_migration.py tests/api/test_ppe_suppliers_service.py tests/api/test_ppe_suppliers_api.py tests/api/test_ppe_supplier_provenance.py tests/api/test_ppe_reorder_service.py tests/api/test_ppe_reorder_api.py tests/api/test_ppe_stock_transfers_service.py tests/api/test_ppe_stock_transfers_api.py tests/api/test_ppe_shortage_service.py tests/api/test_ppe_shortage_api.py tests/api/test_ppe_warehouse_api.py -q`
Expected: all green (new + existing PPE-stock regression).

- [ ] **Step 3: Re-snapshot the OpenAPI baseline**

Run: `$env:PYTHONPATH="backend"; python scripts/ci/check_openapi_snapshot.py --snapshot`
Then verify additive-only: `$env:PYTHONPATH="backend"; python scripts/ci/check_openapi_snapshot.py --compare`
Expected: `--compare` EXIT 0. New routes present: `POST/GET /api/v1/ppe/suppliers`, `GET/PATCH/DELETE /api/v1/ppe/suppliers/{supplier_id}`, `GET /api/v1/ppe/stock/reorder`. Record the new counts (was 820/665 → expect ~826/~672) for the handoff.

- [ ] **Step 4: PG16 gate for `wa08`**

Run: `python scripts/ci/local_gate.py --db-only`
Expected: alembic `upgrade heads` (incl. wa08) + downgrade round-trip + enum-parity green on PG16; ARCH-3 boundaries clean.

- [ ] **Step 5: Update docs**

- `docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md` — P10-06 row: append suppliers prose (directory + provenance + reorder), remove «поставщики» from the «Остаётся» list (leave бюджет безопасности / мобильная выдача).
- `CHANGELOG.md` — new dated entry.
- `AI_IMPLEMENTATION_REPORT.md` — new top handoff block (what shipped, wa08, new routes + counts, invariant untouched, verification results, next slice = бюджет безопасности / мобильная выдача, branch state).

- [ ] **Step 6: Commit**

```bash
git add docs/stabilization/openapi_routes_baseline.json docs/roadmap/PLATFORM_VNEXT_IMPLEMENTATION_PLAN.md CHANGELOG.md AI_IMPLEMENTATION_REPORT.md
git commit -m "docs(p10-06): roadmap + changelog + OpenAPI baseline + handoff for suppliers"
```

---

## Self-Review

**Spec coverage:**
- Layer 1 (model + FKs) → Task 1. Layer 2 (migration wa08) → Task 2. Layer 3 (CRUD service) → Task 3. Layer 5 schemas + Layer 6 CRUD API → Task 4. Provenance (batch supplier + transfer copy) → Task 5. Item preferred_supplier → Task 6. Layer 4 resolution + shortage fields → Task 7. Reorder draft + route → Task 8. Layer 7 frontend → Tasks 9-10. Gates/docs/OpenAPI → Task 11. All spec sections covered.
- Error/edge-cases table: 404 (unknown/cross-tenant/flag-off) → Tasks 4/8 tests; 409 duplicate → Task 4; 400 unknown supplier on batch/item → Tasks 5/6; transfer copies supplier → Task 5; explicit/history/none/soft-deleted resolution → Task 7; unassigned group → Task 8; honest-stock invariant `before==after` → Task 5 (transfer regression) + resolution being read-only.

**Placeholder scan:** No TBD/TODO. Two spots defer an exact detail to the codebase-as-arbiter (Task 3 conflict-path transaction ownership; Task 9 item-PATCH location) — each names the concrete fallback and the test that decides. These are integration-point confirmations, not missing content.

**Type consistency:** `ShortageRow` supplier fields (Task 7) are consumed by `build_reorder_draft` (Task 8) and the shortage schema (Task 7) with identical names. `ReorderLine/ReorderGroup/ReorderDraft` dataclasses (Task 8) mirror `PPEReorderLineRead/GroupRead/DraftRead` schemas (Task 8) field-for-field. `SupplierDto`/`ReorderDraftDto` (Task 9) match `PPESupplierRead`/`PPEReorderDraftRead`. `supplier_id` column name is consistent across model (Task 1), migration (Task 2), schemas (Task 5), transfer copy (Task 5). `_ppe_supplier_conflict` code `PPE_SUPPLIER_CONFLICT` used in Task 4 only.
