# Подрядчики Срез-2 — реестр документов/сертификатов: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone contractor-document registry — CRUD + file reference + expiry classification + daily expiry-notification beat — without touching the Срез-1 admission engine.

**Architecture:** New `ContractorDocument` model (additive table `contractor_documents`, по образцу `TrainingCertificate`) in the existing contractors module; a pure expiry helper reusing `domains/shared.classify`; document endpoints under the existing `/contractors` router (same gate/roles/ABAC); a notify service + daily beat emitting outbox events. `doc_type`/`status` are `VARCHAR` (no PG enum); `file_id` is an app-level `String(36)` reference (no cross-base FK). The admission engine, its projection, and read-model are NOT modified.

**Tech Stack:** Python 3.12 (local 3.13.7 ok), FastAPI, SQLAlchemy 2 async, Alembic, Celery beat, pytest (`-p no:xdist --timeout`).

---

## Источник истины и образцы

- Spec: `docs/superpowers/specs/2026-06-09-contractors-documents-design.md`
- Модель-образец: `TrainingCertificate` — `backend/app/models/models.py:1043-1080`
- Существующие contractor-модели/базы: `backend/app/modules/contractors/models.py` (`TenantBaseModel, SoftDeleteMixin`)
- Expiry helper: `app.domains.shared.classify` → `ContingentItemStatus` (`OK/DUE_SOON/OVERDUE/MISSING`)
- API-роутер + gate/ABAC: `backend/app/api/routes/contractors.py` (`ReaderAccess`/`WriterAccess`/`ContractorsFeatureGate`)
- Notify-образец: `notify_readiness` — `backend/app/services/contractor_admission.py:81-133`
- Beat-образец: `contractors.readiness.tick` — `backend/app/tasks/_core.py:1967-2001`, `backend/app/services/celery_app.py:73-76`
- Events-образец: `backend/app/services/events.py:35-36, 233-234`
- Seed-образец: `backend/app/services/demo_bootstrap.py:155-201`
- Migration-образец: `backend/app/migrations/versions/20260607_med01_medical_domain.py` (head; down_revision цепочки)
- Migration-test-образец: `backend/tests/test_wa01_ppe_stock_batch_migration.py`
- API-test-образец: `tests/api/test_contractors_admission_api.py`
- Service-test-образец: `tests/test_contractor_admission_service.py`

**Test runner (Windows/Py3.13.7, урок [[py313-win-pytest-invocation]]):**
```
python -m pytest <path> -p no:xdist --timeout=120 -q
```

---

## File Structure

| Файл | Действие | Ответственность |
|---|---|---|
| `backend/app/domains/contractors/documents.py` | Create | чистая функция `document_expiry_status` |
| `backend/app/modules/contractors/models.py` | Modify | `+ ContractorDocument` |
| `backend/app/migrations/versions/20260609_con01_contractor_documents.py` | Create | аддитивная таблица |
| `backend/app/api/routes/contractors.py` | Modify | схемы + document-эндпоинты |
| `backend/app/services/events.py` | Modify | 2 EventType + payload-маппинг |
| `backend/app/services/contractor_documents.py` | Create | `notify_document_expiry` |
| `backend/app/tasks/_core.py` | Modify | beat `contractors.documents.tick` |
| `backend/app/services/celery_app.py` | Modify | beat schedule entry |
| `backend/app/services/demo_bootstrap.py` | Modify | seed 3 документа |
| `backend/tests/test_contractor_documents_expiry.py` | Create | Task 1 |
| `backend/tests/test_con01_contractor_documents_migration.py` | Create | Task 2 |
| `tests/api/test_contractor_documents_api.py` | Create | Task 4, 5 |
| `tests/test_contractor_documents_service.py` | Create | Task 6 |
| `tests/test_contractor_documents_tick.py` | Create | Task 7 |
| `tests/test_demo_bootstrap_contractor_documents.py` | Create | Task 8 |

---

## Task 1: Pure expiry helper

**Files:**
- Create: `backend/app/domains/contractors/documents.py`
- Test: `backend/tests/test_contractor_documents_expiry.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_contractor_documents_expiry.py
from datetime import date, timedelta

from app.domains.shared import ContingentItemStatus
from app.domains.contractors.documents import document_expiry_status

TODAY = date(2026, 6, 9)


def test_no_valid_until_is_ok():
    # An open-ended document (no expiry) is OK, NOT missing.
    assert document_expiry_status(None, TODAY) == ContingentItemStatus.OK


def test_future_is_ok():
    assert document_expiry_status(TODAY + timedelta(days=90), TODAY) == ContingentItemStatus.OK


def test_within_window_is_due_soon():
    assert document_expiry_status(TODAY + timedelta(days=10), TODAY) == ContingentItemStatus.DUE_SOON


def test_past_is_overdue():
    assert document_expiry_status(TODAY - timedelta(days=1), TODAY) == ContingentItemStatus.OVERDUE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_contractor_documents_expiry.py -p no:xdist --timeout=120 -q`
Expected: FAIL — `ModuleNotFoundError: app.domains.contractors.documents`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/app/domains/contractors/documents.py
"""Pure expiry classification for contractor documents (no I/O).

A document with NO ``valid_until`` is open-ended → OK (not MISSING). This is the
deliberate difference from admission requirements, where a missing deadline means
"required but unknown". Here, absence of an expiry date is a legitimate state.
"""
from __future__ import annotations

from datetime import date

from app.domains.shared import ContingentItemStatus, classify


def document_expiry_status(valid_until: date | None, today: date) -> ContingentItemStatus:
    """Classify a document's expiry. No date → OK (open-ended), else delegate to classify."""
    if valid_until is None:
        return ContingentItemStatus.OK
    return classify(valid_until, today)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_contractor_documents_expiry.py -p no:xdist --timeout=120 -q`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/contractors/documents.py backend/tests/test_contractor_documents_expiry.py
git commit -m "feat(contractors): pure document expiry classifier (no-date → OK)"
```

---

## Task 2: ContractorDocument model + additive migration

**Files:**
- Modify: `backend/app/modules/contractors/models.py`
- Create: `backend/app/migrations/versions/20260609_con01_contractor_documents.py`
- Test: `backend/tests/test_con01_contractor_documents_migration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_con01_contractor_documents_migration.py
"""Pin: ContractorDocument model + con01 migration shape (Подрядчики Срез-2)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260609_con01_contractor_documents.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("con01_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_model_table_and_columns() -> None:
    from app.modules.contractors.models import ContractorDocument

    assert ContractorDocument.__tablename__ == "contractor_documents"
    cols = set(ContractorDocument.__table__.columns.keys())
    assert {
        "id", "tenant_id", "version", "created_at", "updated_at", "deleted_at",
        "contractor_id", "employee_id", "doc_type", "title", "number",
        "issuing_org", "issued_at", "valid_until", "file_id", "status",
    } <= cols


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260609_con01_contractor_documents"
    assert mod.down_revision == "20260607_med01_medical_domain"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_con01_contractor_documents_migration.py -p no:xdist --timeout=120 -q`
Expected: FAIL — `ImportError: cannot import name 'ContractorDocument'`

- [ ] **Step 3a: Add the model**

Append to `backend/app/modules/contractors/models.py` (after `ContractorIncident`):

```python
class ContractorDocument(TenantBaseModel, SoftDeleteMixin):
    __tablename__ = "contractor_documents"

    contractor_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SET NULL: an employee document survives the employee being removed (kept as a contractor-level record).
    employee_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("contractor_employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # doc_type/status are VARCHAR (validated at the schema layer), NOT PG enums — avoids the
    # enum-label-parity migration class entirely (PR #635–#638).
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    issuing_org: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # file_id is an app-level reference to File (different metadata base) — NO DB FK, mirroring
    # contractor_registry.company_id, to sidestep cross-base FK migration trouble (wa02).
    file_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")

    __table_args__ = (
        Index("ix_contractor_documents_tenant_contractor", "tenant_id", "contractor_id"),
        Index("ix_contractor_documents_tenant_employee", "tenant_id", "employee_id"),
        Index("ix_contractor_documents_tenant_valid", "tenant_id", "valid_until"),
        Index("ix_contractor_documents_tenant_type", "tenant_id", "doc_type"),
    )
```

Update the imports at the top of the file — add `Date` to the sqlalchemy import and `date` to datetime:

```python
from datetime import date, datetime
from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, String, Text
```

- [ ] **Step 3b: Create the migration**

```python
# backend/app/migrations/versions/20260609_con01_contractor_documents.py
"""con01: contractor documents registry (TZ B.14 Срез-2).

Additive. One new table, VARCHAR doc_type/status (no enum types), no cross-base FK
on file. Round-trip-safe: downgrade drops indexes then the table; no orphan enum types.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260609_con01_contractor_documents"
down_revision = "20260607_med01_medical_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contractor_documents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "contractor_id", sa.String(length=36),
            sa.ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "employee_id", sa.String(length=36),
            sa.ForeignKey("contractor_employees.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("number", sa.String(length=128), nullable=True),
        sa.Column("issuing_org", sa.String(length=255), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("file_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
    )
    op.create_index("ix_contractor_documents_tenant_contractor", "contractor_documents", ["tenant_id", "contractor_id"])
    op.create_index("ix_contractor_documents_tenant_employee", "contractor_documents", ["tenant_id", "employee_id"])
    op.create_index("ix_contractor_documents_tenant_valid", "contractor_documents", ["tenant_id", "valid_until"])
    op.create_index("ix_contractor_documents_tenant_type", "contractor_documents", ["tenant_id", "doc_type"])


def downgrade() -> None:
    op.drop_index("ix_contractor_documents_tenant_type", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_valid", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_employee", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_contractor", table_name="contractor_documents")
    op.drop_table("contractor_documents")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_con01_contractor_documents_migration.py -p no:xdist --timeout=120 -q`
Expected: PASS (3 passed)

- [ ] **Step 5: Guard — mapper config still green**

Run: `python -m pytest backend/tests/test_orm_mapper_configuration.py -p no:xdist --timeout=120 -q`
Expected: PASS (the new model must not break `configure_mappers()`; lesson [[orm-duplicate-class-names]])

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/contractors/models.py backend/app/migrations/versions/20260609_con01_contractor_documents.py backend/tests/test_con01_contractor_documents_migration.py
git commit -m "feat(contractors): ContractorDocument model + con01 additive migration"
```

---

## Task 3: Schemas + doc_type vocabulary

**Files:**
- Modify: `backend/app/api/routes/contractors.py`
- Test: (covered by Task 4 API tests; this task only adds schema classes — no standalone test)

- [ ] **Step 1: Add imports and vocabulary**

At the top of `backend/app/api/routes/contractors.py`, extend imports:

```python
from datetime import date, datetime, timezone
from typing import Annotated, Literal
```

Add the model import to the existing `app.modules.contractors.models` import block:

```python
from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocument,
    ContractorEmployee,
    ContractorIncident,
    ContractorRegistry,
)
```

Add the expiry helper import near the admission-service import:

```python
from app.domains.contractors.documents import document_expiry_status
```

Add the vocabulary + schemas (place after `ContractorIncidentCreate`):

```python
DocType = Literal[
    "license", "insurance", "contract", "sro",
    "training_cert", "medical_cert", "access_permit", "qualification",
    "other",
]


class ContractorDocumentCreate(BaseModel):
    contractor_id: str = Field(min_length=1, max_length=36)
    employee_id: str | None = Field(default=None, max_length=36)
    doc_type: DocType
    title: str = Field(min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=128)
    issuing_org: str | None = Field(default=None, max_length=255)
    issued_at: date | None = None
    valid_until: date | None = None
    file_id: str | None = Field(default=None, max_length=36)


class ContractorDocumentPatch(BaseModel):
    doc_type: DocType | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    number: str | None = Field(default=None, max_length=128)
    issuing_org: str | None = Field(default=None, max_length=255)
    issued_at: date | None = None
    valid_until: date | None = None
    file_id: str | None = Field(default=None, max_length=36)
    status: str | None = Field(default=None, max_length=32)
```

- [ ] **Step 2: Verify import-time sanity**

Run: `python -c "import app.api.routes.contractors"`
Expected: no error (exit 0).

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/routes/contractors.py
git commit -m "feat(contractors): document schemas + doc_type vocabulary"
```

---

## Task 4: Document CRUD endpoints

**Files:**
- Modify: `backend/app/api/routes/contractors.py`
- Test: `tests/api/test_contractor_documents_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_contractor_documents_api.py
"""Contractor document registry CRUD + isolation + feature-gate."""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.modules.contractors.models import ContractorEmployee, ContractorRegistry

TODAY = date.today()


async def _seed_contractor(sessionmaker, data_factory) -> tuple[str, str]:
    """Return (contractor_id, employee_id) in the default tenant."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        contractor = ContractorRegistry(tenant_id=str(tenant.id), name="Doc Contractor")
        session.add(contractor)
        await session.flush()
        emp = ContractorEmployee(
            tenant_id=str(tenant.id), contractor_id=str(contractor.id), full_name="Doc Worker",
        )
        session.add(emp)
        await session.commit()
        return str(contractor.id), str(emp.id)


@pytest.mark.asyncio
async def test_create_and_get_document(async_client: AsyncClient, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={
            "contractor_id": contractor_id,
            "doc_type": "license",
            "title": "СРО допуск",
            "valid_until": (TODAY + timedelta(days=90)).isoformat(),
        },
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    doc_id = resp.json()["id"]

    got = await async_client.get(f"/api/v1/contractors/documents/{doc_id}", headers=headers)
    assert got.status_code == status.HTTP_200_OK, got.text
    body = got.json()
    assert body["doc_type"] == "license"
    assert body["expiry_status"] == "ok"


@pytest.mark.asyncio
async def test_metadata_only_document_without_file(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "other", "title": "Без файла"},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    assert resp.json()["file_id"] is None
    assert resp.json()["expiry_status"] == "ok"  # no valid_until → ok


@pytest.mark.asyncio
async def test_invalid_doc_type_returns_422(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "bogus", "title": "x"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_employee_mismatch_returns_422(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    other_contractor, other_emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        "/api/v1/contractors/documents",
        headers=headers,
        json={"contractor_id": contractor_id, "employee_id": other_emp, "doc_type": "medical_cert", "title": "x"},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_list_filters_by_contractor(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(
        "/api/v1/contractors/documents", headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "sro", "title": "A"},
    )
    resp = await async_client.get(
        f"/api/v1/contractors/documents?contractor_id={contractor_id}", headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["expiry_status"] == "ok"


@pytest.mark.asyncio
async def test_patch_and_soft_delete(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/contractors/documents", headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "license", "title": "Old"},
    )
    doc_id = created.json()["id"]

    patched = await async_client.patch(
        f"/api/v1/contractors/documents/{doc_id}", headers=headers, json={"title": "New"},
    )
    assert patched.status_code == status.HTTP_200_OK, patched.text
    assert patched.json()["title"] == "New"

    deleted = await async_client.delete(f"/api/v1/contractors/documents/{doc_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    gone = await async_client.get(f"/api/v1/contractors/documents/{doc_id}", headers=headers)
    assert gone.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_cross_tenant_document_is_404(async_client, sessionmaker, data_factory, make_auth_headers):
    """A document created in tenant A is invisible/404 to tenant B."""
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    created = await async_client.post(
        "/api/v1/contractors/documents", headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "license", "title": "Secret"},
    )
    doc_id = created.json()["id"]
    other_headers = await make_auth_headers(RoleEnum.ADMIN, tenant_slug="other-tenant")
    resp = await async_client.get(f"/api/v1/contractors/documents/{doc_id}", headers=other_headers)
    assert resp.status_code == status.HTTP_404_NOT_FOUND, resp.text
```

> **Note for implementer:** verify the exact `make_auth_headers` cross-tenant signature against `tests/api/test_contractors_admission_api.py` / `conftest.py`. If a second tenant cannot be minted via `tenant_slug=`, seed it via `data_factory` and adapt `test_cross_tenant_document_is_404` to that helper — keep the assertion (cross-tenant → 404).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_contractor_documents_api.py -p no:xdist --timeout=120 -q`
Expected: FAIL — 404/405 (routes not defined yet)

- [ ] **Step 3: Implement the CRUD endpoints**

Add to `backend/app/api/routes/contractors.py` (after the admission endpoints, end of file). The helper `_document_body` computes `expiry_status` via the pure helper:

```python
# ---------------------------------------------------------------------------
# Document registry
# ---------------------------------------------------------------------------


def _document_body(doc: ContractorDocument) -> dict:
    today = datetime.now(timezone.utc).date()
    return {
        "id": doc.id,
        "contractor_id": doc.contractor_id,
        "employee_id": doc.employee_id,
        "doc_type": doc.doc_type,
        "title": doc.title,
        "number": doc.number,
        "issuing_org": doc.issuing_org,
        "issued_at": doc.issued_at.isoformat() if doc.issued_at else None,
        "valid_until": doc.valid_until.isoformat() if doc.valid_until else None,
        "file_id": doc.file_id,
        "status": doc.status,
        "expiry_status": document_expiry_status(doc.valid_until, today).value,
    }


async def _fetch_document(session: AsyncSession, tenant: Tenant, document_id: str) -> ContractorDocument:
    row = (
        await session.execute(
            select(ContractorDocument).where(
                ContractorDocument.id == document_id,
                ContractorDocument.tenant_id == str(tenant.id),
                ContractorDocument.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return row


async def _validate_employee_belongs(
    session: AsyncSession, tenant: Tenant, contractor_id: str, employee_id: str
) -> None:
    """422 if employee_id does not belong to contractor_id within the tenant."""
    emp = (
        await session.execute(
            select(ContractorEmployee).where(
                ContractorEmployee.id == employee_id,
                ContractorEmployee.tenant_id == str(tenant.id),
                ContractorEmployee.contractor_id == contractor_id,
                ContractorEmployee.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if emp is None:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "employee_id does not belong to contractor_id",
        )


@router.get("/documents", dependencies=[ContractorsFeatureGate])
async def list_contractor_documents(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    contractor_id: str | None = Query(default=None),
    employee_id: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
) -> dict:
    if contractor_id:
        access.ensure_abac(contractor_id=contractor_id, action="read contractors")
    stmt = select(ContractorDocument).where(
        ContractorDocument.tenant_id == str(tenant.id),
        ContractorDocument.deleted_at.is_(None),
    )
    if contractor_id:
        stmt = stmt.where(ContractorDocument.contractor_id == contractor_id)
    if employee_id:
        stmt = stmt.where(ContractorDocument.employee_id == employee_id)
    if doc_type:
        stmt = stmt.where(ContractorDocument.doc_type == doc_type)
    if status_filter:
        stmt = stmt.where(ContractorDocument.status == status_filter)
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorDocument.contractor_id.in_(contractor_ids))
    items = list((await session.execute(stmt.order_by(ContractorDocument.created_at.desc()))).scalars().all())
    return {"items": [_document_body(d) for d in items], "total": len(items)}


@router.post("/documents", status_code=status.HTTP_201_CREATED, dependencies=[ContractorsFeatureGate])
async def create_contractor_document(
    payload: ContractorDocumentCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> dict:
    access.ensure_abac(contractor_id=payload.contractor_id, action="manage contractors")
    if payload.employee_id:
        await _validate_employee_belongs(session, tenant, payload.contractor_id, payload.employee_id)
    row = ContractorDocument(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _document_body(row)


@router.get("/documents/expiring", dependencies=[ContractorsFeatureGate])
async def list_expiring_contractor_documents(
    tenant: TenantDep,
    session: SessionDep,
    access: ReaderAccess,
    contractor_id: str | None = Query(default=None),
) -> dict:
    """Advisory: documents whose expiry_status is DUE_SOON or OVERDUE."""
    if contractor_id:
        access.ensure_abac(contractor_id=contractor_id, action="read contractors")
    stmt = select(ContractorDocument).where(
        ContractorDocument.tenant_id == str(tenant.id),
        ContractorDocument.deleted_at.is_(None),
        ContractorDocument.valid_until.is_not(None),
    )
    if contractor_id:
        stmt = stmt.where(ContractorDocument.contractor_id == contractor_id)
    contractor_ids = [str(v) for v in access.claims.get("contractor_ids", []) if v]
    if contractor_ids:
        stmt = stmt.where(ContractorDocument.contractor_id.in_(contractor_ids))
    today = datetime.now(timezone.utc).date()
    flagged = [
        _document_body(d)
        for d in (await session.execute(stmt)).scalars().all()
        if document_expiry_status(d.valid_until, today) in (
            ContingentItemStatus.DUE_SOON, ContingentItemStatus.OVERDUE,
        )
    ]
    return {"items": flagged, "total": len(flagged)}


@router.get("/documents/{document_id}", dependencies=[ContractorsFeatureGate])
async def get_contractor_document(document_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> dict:
    row = await _fetch_document(session, tenant, document_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="read contractors")
    return _document_body(row)


@router.patch("/documents/{document_id}", dependencies=[ContractorsFeatureGate])
async def patch_contractor_document(
    document_id: str, payload: ContractorDocumentPatch, tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> dict:
    row = await _fetch_document(session, tenant, document_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="manage contractors")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    await session.commit()
    await session.refresh(row)
    return _document_body(row)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None, dependencies=[ContractorsFeatureGate])
async def archive_contractor_document(document_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess):
    row = await _fetch_document(session, tenant, document_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="manage contractors")
    row.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return None
```

Add `ContingentItemStatus` to the imports (used by `/documents/expiring`):

```python
from app.domains.shared import ContingentItemStatus
```

> **Routing note:** `/documents/expiring` is declared BEFORE `/documents/{document_id}` so the literal path wins over the path-param route. Keep that order.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/api/test_contractor_documents_api.py -p no:xdist --timeout=120 -q`
Expected: PASS (7 passed). If the cross-tenant helper differs, adapt per the Step-1 note (keep the 404 assertion).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/contractors.py tests/api/test_contractor_documents_api.py
git commit -m "feat(contractors): document CRUD + expiring endpoints (expiry_status in body)"
```

---

## Task 5: Expiring-endpoint coverage (DUE_SOON / OVERDUE)

**Files:**
- Test: `tests/api/test_contractor_documents_api.py` (append)

> The endpoint was implemented in Task 4; this task pins its filtering behavior.

- [ ] **Step 1: Append the failing test**

```python
@pytest.mark.asyncio
async def test_expiring_endpoint_flags_due_soon_and_overdue(async_client, sessionmaker, data_factory, make_auth_headers):
    contractor_id, _emp = await _seed_contractor(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    async def _mk(title, days):
        return await async_client.post(
            "/api/v1/contractors/documents", headers=headers,
            json={
                "contractor_id": contractor_id, "doc_type": "training_cert", "title": title,
                "valid_until": (TODAY + timedelta(days=days)).isoformat(),
            },
        )

    await _mk("Future", 90)     # OK — excluded
    await _mk("Soon", 10)       # DUE_SOON — included
    await _mk("Past", -5)       # OVERDUE — included
    # open-ended (no valid_until) — excluded
    await async_client.post(
        "/api/v1/contractors/documents", headers=headers,
        json={"contractor_id": contractor_id, "doc_type": "other", "title": "Open"},
    )

    resp = await async_client.get(
        f"/api/v1/contractors/documents/expiring?contractor_id={contractor_id}", headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["total"] == 2
    titles = {item["title"] for item in body["items"]}
    assert titles == {"Soon", "Past"}
```

- [ ] **Step 2: Run test**

Run: `python -m pytest "tests/api/test_contractor_documents_api.py::test_expiring_endpoint_flags_due_soon_and_overdue" -p no:xdist --timeout=120 -q`
Expected: PASS (endpoint already implemented in Task 4)

- [ ] **Step 3: Commit**

```bash
git add tests/api/test_contractor_documents_api.py
git commit -m "test(contractors): pin expiring-document filtering (due_soon + overdue)"
```

---

## Task 6: Expiry-notification service + events

**Files:**
- Modify: `backend/app/services/events.py`
- Create: `backend/app/services/contractor_documents.py`
- Test: `tests/test_contractor_documents_service.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contractor_documents_service.py
"""notify_document_expiry: enqueue only for DUE_SOON/OVERDUE, idempotent per day."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.contractors.models import ContractorDocument, ContractorRegistry

TODAY = date.today()


async def _seed(session, tenant_id: str) -> str:
    contractor = ContractorRegistry(tenant_id=tenant_id, name="Notif Contractor")
    session.add(contractor)
    await session.flush()
    # OK (future) — skipped
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="license", title="Future",
        valid_until=TODAY + timedelta(days=90),
    ))
    # open-ended — skipped
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="other", title="Open",
    ))
    # DUE_SOON — enqueued
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="medical_cert", title="Soon",
        valid_until=TODAY + timedelta(days=10),
    ))
    # OVERDUE — enqueued
    session.add(ContractorDocument(
        tenant_id=tenant_id, contractor_id=contractor.id, doc_type="access_permit", title="Past",
        valid_until=TODAY - timedelta(days=3),
    ))
    await session.commit()
    return contractor.id


@pytest.mark.asyncio
async def test_notify_enqueues_due_soon_and_overdue_only(sessionmaker, data_factory):
    from app.services.contractor_documents import notify_document_expiry

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed(session, tid)
        count = await notify_document_expiry(session, tenant_id=tid)
        await session.commit()
    assert count == 2, f"Expected 2 (DUE_SOON + OVERDUE), got {count}"


@pytest.mark.asyncio
async def test_notify_is_idempotent_same_day(sessionmaker, data_factory):
    from app.services.contractor_documents import notify_document_expiry

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed(session, tid)
        first = await notify_document_expiry(session, tenant_id=tid)
        await session.commit()
        second = await notify_document_expiry(session, tenant_id=tid)
        await session.commit()
    assert first == 2
    assert second == 0, "Same-day re-run must not duplicate events"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_contractor_documents_service.py -p no:xdist --timeout=120 -q`
Expected: FAIL — `ModuleNotFoundError: app.services.contractor_documents`

- [ ] **Step 3a: Add the events**

In `backend/app/services/events.py`, after `CONTRACTOR_READINESS_WARNING` (line ~36):

```python
    CONTRACTOR_DOCUMENT_EXPIRING = "contractor.document_expiring"
    CONTRACTOR_DOCUMENT_EXPIRED = "contractor.document_expired"
```

And in the payload-type map after `CONTRACTOR_READINESS_WARNING: InternalEventPayload` (line ~234):

```python
    EventType.CONTRACTOR_DOCUMENT_EXPIRING: InternalEventPayload,
    EventType.CONTRACTOR_DOCUMENT_EXPIRED: InternalEventPayload,
```

- [ ] **Step 3b: Write the service**

```python
# backend/app/services/contractor_documents.py
"""Contractor-document expiry notifications.

Mirrors ``notify_readiness`` (contractor_admission.py): load tenant documents that
carry a ``valid_until``, classify, enqueue an outbox event for DUE_SOON / OVERDUE.
Idempotent per (document, status, UTC date).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contractors.documents import document_expiry_status
from app.domains.shared import ContingentItemStatus
from app.modules.contractors.models import ContractorDocument
from app.services.events import EventType
from app.services.outbox import OutboxService

_STATUS_EVENT = {
    ContingentItemStatus.DUE_SOON: EventType.CONTRACTOR_DOCUMENT_EXPIRING,
    ContingentItemStatus.OVERDUE: EventType.CONTRACTOR_DOCUMENT_EXPIRED,
}


async def notify_document_expiry(session: AsyncSession, *, tenant_id: str) -> int:
    """Enqueue expiry events for the tenant's documents. Returns count enqueued."""
    stmt = select(ContractorDocument).where(
        ContractorDocument.tenant_id == tenant_id,
        ContractorDocument.deleted_at.is_(None),
        ContractorDocument.valid_until.is_not(None),
    )
    documents = list((await session.execute(stmt)).scalars().all())

    today = datetime.now(timezone.utc).date()
    outbox = OutboxService(session)
    count = 0
    for doc in documents:
        expiry = document_expiry_status(doc.valid_until, today)
        event_type = _STATUS_EVENT.get(expiry)
        if event_type is None:
            continue
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=event_type.value,
            idempotency_key=f"contractor-document:{doc.id}:{expiry.value}:{today.isoformat()}",
            payload={
                "tenant_id": tenant_id,
                "metadata": {
                    "document_id": doc.id,
                    "contractor_id": doc.contractor_id,
                    "employee_id": doc.employee_id,
                    "doc_type": doc.doc_type,
                    "valid_until": doc.valid_until.isoformat(),
                    "status": expiry.value,
                },
            },
        )
        count += 1
    return count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_contractor_documents_service.py -p no:xdist --timeout=120 -q`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/events.py backend/app/services/contractor_documents.py tests/test_contractor_documents_service.py
git commit -m "feat(contractors): document expiry notifications (DUE_SOON/OVERDUE outbox)"
```

---

## Task 7: Daily beat tick

**Files:**
- Modify: `backend/app/tasks/_core.py`
- Modify: `backend/app/services/celery_app.py`
- Test: `tests/test_contractor_documents_tick.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contractor_documents_tick.py
"""contractors.documents.tick: drives notify_document_expiry across active tenants."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.modules.contractors.models import ContractorDocument, ContractorRegistry

TODAY = date.today()


@pytest.mark.asyncio
async def test_documents_tick_enqueues(sessionmaker, data_factory):
    from app.tasks._core import _contractors_documents_tick

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Tick Contractor")
        session.add(contractor)
        await session.flush()
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=contractor.id, doc_type="medical_cert", title="Soon",
            valid_until=TODAY + timedelta(days=10),
        ))
        await session.commit()

    total = await _contractors_documents_tick()
    assert total >= 1
```

> **Implementer note:** confirm the async-helper test pattern matches the existing tick test (`tests/test_contractor_readiness_tick.py` if present, else `backend/tests/test_prescriptions_escalate_tick.py`). Mirror its tenant/fixture setup exactly — tick helpers resolve active tenants from the DB, so the seeded tenant must be `is_active=True` (data_factory default).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_contractor_documents_tick.py -p no:xdist --timeout=120 -q`
Expected: FAIL — `ImportError: cannot import name '_contractors_documents_tick'`

- [ ] **Step 3a: Add the task** in `backend/app/tasks/_core.py` (after `_contractors_readiness_tick`, ~line 2001):

```python
@celery_app.task(
    name="contractors.documents.tick",
    autoretry_for=RETRYABLE_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def contractors_documents_tick() -> int:
    return _run_coroutine(_contractors_documents_tick())


async def _contractors_documents_tick() -> int:
    from app.services.contractor_documents import notify_document_expiry

    async with AsyncSessionLocal(tenant=settings.default_tenant_slug) as session:
        tenants = list(
            (await session.execute(select(Tenant).where(Tenant.is_active.is_(True)))).scalars().all()
        )
    total = 0
    for tenant in tenants:
        with tenant_context(tenant.slug):
            ensure_tenant_schema(tenant.slug)
            async with session_scope(tenant=tenant.slug) as session:
                tenant_id, _scope = await _resolve_task_tenant_scope(session, tenant.slug)
                # Enqueue then commit — outbox events are atomic with the read (notify dedups
                # by (document, status, day), so autoretry is safe).
                total += await notify_document_expiry(session, tenant_id=tenant_id)
                await session.commit()
    return total
```

- [ ] **Step 3b: Register the beat** in `backend/app/services/celery_app.py` (after the `contractors-readiness-daily` entry, ~line 76):

```python
    "contractors-documents-daily": {
        "task": "contractors.documents.tick",
        "schedule": crontab(hour=3, minute=45),
    },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_contractor_documents_tick.py -p no:xdist --timeout=120 -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/tasks/_core.py backend/app/services/celery_app.py tests/test_contractor_documents_tick.py
git commit -m "feat(contractors): daily contractors.documents.tick beat"
```

---

## Task 8: Demo seed

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`
- Test: `tests/test_demo_bootstrap_contractor_documents.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_demo_bootstrap_contractor_documents.py
"""Demo seed creates 3 contractor documents with valid/expiring/expired statuses."""
from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.domains.contractors.documents import document_expiry_status
from app.domains.shared import ContingentItemStatus
from app.modules.contractors.models import ContractorDocument


@pytest.mark.asyncio
async def test_demo_seed_creates_three_documents(sessionmaker, data_factory):
    from app.services.demo_bootstrap import _seed_contractor_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        from app.modules.contractors.models import ContractorEmployee, ContractorRegistry
        contractor = ContractorRegistry(tenant_id=tid, name="Seed Doc Contractor")
        session.add(contractor)
        await session.flush()
        emp = ContractorEmployee(tenant_id=tid, contractor_id=contractor.id, full_name="Seed Worker")
        session.add(emp)
        await session.flush()

        await _seed_contractor_documents(session, tid, contractor.id, emp.id)
        await session.commit()

        docs = list((await session.execute(
            select(ContractorDocument).where(ContractorDocument.tenant_id == tid)
        )).scalars().all())

    assert len(docs) == 3
    today = date.today()
    statuses = {document_expiry_status(d.valid_until, today) for d in docs}
    assert ContingentItemStatus.OK in statuses
    assert ContingentItemStatus.DUE_SOON in statuses
    assert ContingentItemStatus.OVERDUE in statuses
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_demo_bootstrap_contractor_documents.py -p no:xdist --timeout=120 -q`
Expected: FAIL — `ImportError: cannot import name '_seed_contractor_documents'`

- [ ] **Step 3a: Add the seed helper** to `backend/app/services/demo_bootstrap.py`. Extend the model import:

```python
from app.modules.contractors.models import (
    ComplianceStatus, ContractorDocument, ContractorEmployee, ContractorRegistry,
)
```

Add `date, timedelta` to the datetime import if not present (`from datetime import date, datetime, timedelta, timezone`). Add the helper:

```python
async def _seed_contractor_documents(session, tenant_db_id: str, contractor_id: str, employee_id: str) -> None:
    """Seed 3 demo documents: valid (org), expiring (employee), expired (employee)."""
    today = date.today()
    session.add(ContractorDocument(
        tenant_id=tenant_db_id, contractor_id=contractor_id, doc_type="sro",
        title="СРО допуск (демо)", valid_until=today + timedelta(days=180), status="active",
    ))
    session.add(ContractorDocument(
        tenant_id=tenant_db_id, contractor_id=contractor_id, employee_id=employee_id,
        doc_type="medical_cert", title="Медзаключение (истекает)",
        valid_until=today + timedelta(days=15), status="active",
    ))
    session.add(ContractorDocument(
        tenant_id=tenant_db_id, contractor_id=contractor_id, employee_id=employee_id,
        doc_type="access_permit", title="Допуск на объект (просрочен)",
        valid_until=today - timedelta(days=5), status="active",
    ))
```

- [ ] **Step 3b: Wire the helper into the bootstrap.** In `bootstrap_demo_tenant`, the demo contractor + employees are created inside the `if contractor is None:` block (`demo_bootstrap.py:165-201`). Capture the first employee and call the seed helper at the end of that block (before `await ensure_default_packs`). Replace the `ContractorEmployee(... "Готовый Иван" ...)` `session.add(...)` so the row is captured:

```python
            ready_emp = ContractorEmployee(
                tenant_id=tenant_db_id,
                contractor_id=contractor.id,
                full_name="Готовый Иван",
                access_status=ComplianceStatus.VALID,
                training_status=ComplianceStatus.VALID,
                medical_status=ComplianceStatus.VALID,
                last_training_at=now,
                next_medical_at=now + timedelta(days=200),
            )
            session.add(ready_emp)
```

Then, after the "Просроченный Пётр" `session.add(...)` block, add:

```python
            await session.flush()  # assign ids before seeding documents
            await _seed_contractor_documents(session, tenant_db_id, contractor.id, ready_emp.id)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_demo_bootstrap_contractor_documents.py -p no:xdist --timeout=120 -q`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demo_bootstrap.py tests/test_demo_bootstrap_contractor_documents.py
git commit -m "feat(contractors): demo-seed 3 contractor documents (valid/expiring/expired)"
```

---

## Final verification (after all tasks)

- [ ] **Контурный когорт зелёный:**

```
python -m pytest backend/tests/test_contractor_documents_expiry.py backend/tests/test_con01_contractor_documents_migration.py tests/api/test_contractor_documents_api.py tests/test_contractor_documents_service.py tests/test_contractor_documents_tick.py tests/test_demo_bootstrap_contractor_documents.py -p no:xdist --timeout=180 -q
```
Expected: all PASS.

- [ ] **Смежная регрессия (движок Среза-1 не затронут):**

```
python -m pytest tests/api/test_contractors_admission_api.py tests/test_contractor_admission_service.py tests/test_contractor_readiness_projection.py backend/tests/test_contractors_lifecycle.py backend/tests/test_orm_mapper_configuration.py -p no:xdist --timeout=180 -q
```
Expected: all PASS (zero regression).

- [ ] **Записать handoff** в `AI_IMPLEMENTATION_REPORT.md` (новый верхний блок) + обновить память [[tz-section-b-ground-truth]].

---

## Self-Review notes (план ↔ спек)

- **Spec §3.1 модель** → Task 2. **§3.2 expiry helper** → Task 1. **§3.3 миграция** → Task 2. **§3.4 API (CRUD + expiring)** → Tasks 3,4,5. **§3.5 notify-сервис** → Task 6. **§3.6 beat** → Task 7. **§3.7 события** → Task 6. **§3.8 seed** → Task 8.
- **§5 инварианты:** tenant-isolation (Task 4 cross-tenant 404), ABAC (`contractor_ids` фильтр в list/expiring), feature-gate (`ContractorsFeatureGate` на всех document-роутах), employee-mismatch 422 (Task 4), doc_type 422 (Pydantic `Literal`, Task 4), идемпотентность (Task 6).
- **Type-consistency:** `document_expiry_status(valid_until, today)` — единая сигнатура во всех тасках; `ContingentItemStatus.{OK,DUE_SOON,OVERDUE}` и их `.value` (`ok/due_soon/overdue`) — согласованы; `_STATUS_EVENT` маппинг ↔ `EventType.CONTRACTOR_DOCUMENT_{EXPIRING,EXPIRED}`.
- **Анти-«театр»:** документы имеют реальный поток (CRUD + expiry-вычисление + ежедневные уведомления), не просто схему.
- **Движок допуска НЕ изменяется** — подтверждается смежной регрессией в финальной верификации.
