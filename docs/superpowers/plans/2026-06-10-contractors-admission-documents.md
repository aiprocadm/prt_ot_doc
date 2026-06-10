# Подрядчики Срез-3 — документ→вердикт допуска: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Конфигурируемые «требуемые типы документов» (тенант-политика) гатят вердикт допуска подрядного сотрудника: отсутствующий/просроченный обязательный документ → `BLOCKED` → `POST /admit` = 409.

**Architecture:** Подход A из спеки — расширить чистый `evaluate_employee` четвёртым измерением `documents` (опциональные параметры, back-compat), завести session-aware загрузчик `evaluate_with_documents` как единственный doc-aware путь, через который идут `enforce`/`notify`/`/admit`/`/readiness`/проекция. Новая аддитивная таблица `contractor_document_requirement`; checklist-API кормит будущий wizard.

**Tech Stack:** Python 3.12 (CI; локально Py3.13.7/.venv), FastAPI, SQLAlchemy async, Alembic, pytest. Спека: `docs/superpowers/specs/2026-06-10-contractors-admission-documents-design.md`.

**Ветка:** `feat/contractors-admission-documents` (стопкой поверх `feat/contractors-documents` / Срез-2).

**Локальный запуск тестов (Win/Py3.13):** через PowerShell с редиректом в файл (см. [[py313_win_pytest_invocation]]):
`$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest <путь>::<тест> -p no:xdist --timeout=300 > _t.txt 2>&1; "EXIT=$LASTEXITCODE"` — затем читать `_t.txt`. Канон Py3.12 = CI.

---

## File Structure

**Создать:**
- `backend/app/migrations/versions/20260610_con02_contractor_document_requirements.py` — аддитивная миграция.
- `backend/tests/test_con02_contractor_document_requirements_migration.py` — пины модели/миграции.
- `backend/tests/test_contractor_document_requirements.py` — pure unit-тесты (`requirement_status`, `evaluate_employee` с документами).
- `tests/api/test_contractor_document_requirements_api.py` — CRUD requirements + checklist + e2e gating.
- `tests/test_contractor_admission_with_documents.py` — сервис-загрузчик `evaluate_with_documents`.

**Изменить:**
- `backend/app/domains/contractors/documents.py` — `_PREFERENCE`, `best_document`, `requirement_status`.
- `backend/app/domains/contractors/lifecycle.py` — `DocumentRequirement` + параметры `evaluate_employee`.
- `backend/app/modules/contractors/models.py` — модель `ContractorDocumentRequirement` (+ `Boolean` в импорт).
- `backend/app/services/contractor_admission.py` — `_load_requirements`, `evaluate_with_documents`, `load_document_checklist`; переключить `enforce`/`notify_readiness`.
- `backend/app/api/routes/contractors.py` — схемы + requirements CRUD + checklist; `/admit` и `/readiness` через загрузчик.
- `backend/app/modules/projections/services.py` — `rebuild` через загрузчик; наполнить `missing_docs_count`.
- `backend/app/services/demo_bootstrap.py` — seed 2 правил.

---

## Task 1: Pure `requirement_status` + `best_document`

**Files:**
- Modify: `backend/app/domains/contractors/documents.py`
- Test: `backend/tests/test_contractor_document_requirements.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_contractor_document_requirements.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from app.domains.shared import ContingentItemStatus
from app.domains.contractors.documents import requirement_status, best_document

TODAY = date(2026, 6, 10)


@dataclass
class _Doc:
    valid_until: date | None
    id: str = "d"
    doc_type: str = "license"


def test_no_candidates_is_missing():
    assert requirement_status([], TODAY) == ContingentItemStatus.MISSING


def test_open_ended_candidate_is_ok():
    assert requirement_status([_Doc(None)], TODAY) == ContingentItemStatus.OK


def test_future_candidate_is_ok():
    assert requirement_status([_Doc(TODAY + timedelta(days=90))], TODAY) == ContingentItemStatus.OK


def test_within_window_is_due_soon():
    assert requirement_status([_Doc(TODAY + timedelta(days=10))], TODAY) == ContingentItemStatus.DUE_SOON


def test_past_is_overdue():
    assert requirement_status([_Doc(TODAY - timedelta(days=1))], TODAY) == ContingentItemStatus.OVERDUE


def test_best_of_multiple_valid_beats_expired():
    docs = [_Doc(TODAY - timedelta(days=5), id="old"), _Doc(TODAY + timedelta(days=90), id="new")]
    assert requirement_status(docs, TODAY) == ContingentItemStatus.OK
    assert best_document(docs, TODAY).id == "new"


def test_best_document_none_when_empty():
    assert best_document([], TODAY) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_contractor_document_requirements.py -v`
Expected: FAIL — `ImportError: cannot import name 'requirement_status'`.

- [ ] **Step 3: Write minimal implementation**

Append to `backend/app/domains/contractors/documents.py` (keep existing `document_expiry_status`):

```python
from collections.abc import Sequence
from typing import Protocol


class _DocLike(Protocol):
    valid_until: date | None


# Best-first preference: a single OK candidate satisfies; else DUE_SOON; else OVERDUE.
_PREFERENCE = {
    ContingentItemStatus.OK: 0,
    ContingentItemStatus.DUE_SOON: 1,
    ContingentItemStatus.OVERDUE: 2,
}


def best_document(candidates: Sequence[_DocLike], today: date) -> _DocLike | None:
    """The most-OK candidate (OK > DUE_SOON > OVERDUE), or None if there are none."""
    if not candidates:
        return None
    return min(candidates, key=lambda d: _PREFERENCE[document_expiry_status(d.valid_until, today)])


def requirement_status(candidates: Sequence[_DocLike], today: date) -> ContingentItemStatus:
    """Status of a requirement given its satisfying candidates. No candidate → MISSING."""
    best = best_document(candidates, today)
    if best is None:
        return ContingentItemStatus.MISSING
    return document_expiry_status(best.valid_until, today)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_contractor_document_requirements.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/domains/contractors/documents.py backend/tests/test_contractor_document_requirements.py
git commit -m "feat(contractors): pure requirement_status + best_document classifier"
```

---

## Task 2: `ContractorDocumentRequirement` model + con02 migration

**Files:**
- Modify: `backend/app/modules/contractors/models.py`
- Create: `backend/app/migrations/versions/20260610_con02_contractor_document_requirements.py`
- Test: `backend/tests/test_con02_contractor_document_requirements_migration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_con02_contractor_document_requirements_migration.py
from __future__ import annotations

import importlib.util
from pathlib import Path

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "app" / "migrations" / "versions" / "20260610_con02_contractor_document_requirements.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("con02_mig", _MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_model_table_and_columns() -> None:
    from app.modules.contractors.models import ContractorDocumentRequirement

    assert ContractorDocumentRequirement.__tablename__ == "contractor_document_requirement"
    cols = set(ContractorDocumentRequirement.__table__.columns.keys())
    assert {
        "id", "tenant_id", "version", "created_at", "updated_at", "deleted_at",
        "doc_type", "scope", "mandatory",
    } <= cols


def test_migration_revision_metadata() -> None:
    mod = _load_migration()
    assert mod.revision == "20260610_con02_contractor_document_requirements"
    assert mod.down_revision == "20260609_con01_contractor_documents"
    assert mod.depends_on is None


def test_migration_has_upgrade_and_downgrade() -> None:
    mod = _load_migration()
    assert callable(mod.upgrade)
    assert callable(mod.downgrade)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_con02_contractor_document_requirements_migration.py -v`
Expected: FAIL — `ImportError: cannot import name 'ContractorDocumentRequirement'` and missing migration file.

- [ ] **Step 3a: Add the model**

In `backend/app/modules/contractors/models.py`, extend the sqlalchemy import to include `Boolean`:

```python
from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Index, String, Text
```

Append at the end of the file:

```python
class ContractorDocumentRequirement(TenantBaseModel, SoftDeleteMixin):
    """Tenant-level policy: which document types are required for admission, and how.

    scope routes where a satisfying document is looked for: "company" → contractor-level
    documents (employee_id IS NULL); "employee" → the employee's own documents.
    doc_type/scope are VARCHAR (validated at the schema layer), NOT PG enums — keeps the
    table out of the enum-label-parity migration class (PR #635–#638).
    """

    __tablename__ = "contractor_document_requirement"

    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)  # "company" | "employee"
    mandatory: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa_true())

    __table_args__ = (
        Index("ix_contractor_doc_req_tenant_type", "tenant_id", "doc_type"),
    )
```

Add the `sa_true` import near the top (after the existing imports):

```python
from sqlalchemy import true as sa_true
```

> **Uniqueness note:** `(tenant_id, doc_type, scope)` uniqueness among non-deleted rows is enforced
> at the service layer (Task 5 POST returns 409 on duplicate), NOT a partial-unique index — partial
> indexes render differently per dialect and soft-delete would block re-creating a deleted rule.

- [ ] **Step 3b: Create the migration**

```python
# backend/app/migrations/versions/20260610_con02_contractor_document_requirements.py
"""con02: contractor document requirements policy (TZ B.14 Срез-3).

Additive. One new table, VARCHAR doc_type/scope (no enum types), no cross-base FK.
Round-trip-safe: downgrade drops the index then the table; no orphan enum types.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260610_con02_contractor_document_requirements"
down_revision = "20260609_con01_contractor_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contractor_document_requirement",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doc_type", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("mandatory", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(
        "ix_contractor_doc_req_tenant_type",
        "contractor_document_requirement",
        ["tenant_id", "doc_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_contractor_doc_req_tenant_type", table_name="contractor_document_requirement")
    op.drop_table("contractor_document_requirement")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_con02_contractor_document_requirements_migration.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Verify the migration chain has a single head**

Run: `python -m pytest backend/tests/test_con01_contractor_documents_migration.py backend/tests/test_con02_contractor_document_requirements_migration.py -v`
Expected: PASS (6 passed). (con02.down_revision == con01.revision keeps a linear chain.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/contractors/models.py backend/app/migrations/versions/20260610_con02_contractor_document_requirements.py backend/tests/test_con02_contractor_document_requirements_migration.py
git commit -m "feat(contractors): ContractorDocumentRequirement model + con02 additive migration"
```

---

## Task 3: Extend pure `evaluate_employee` with the documents dimension

**Files:**
- Modify: `backend/app/domains/contractors/lifecycle.py`
- Test: `backend/tests/test_contractor_document_requirements.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_contractor_document_requirements.py`:

```python
from types import SimpleNamespace

from app.domains.contractors.lifecycle import (
    DocumentRequirement,
    ReadinessStatus,
    evaluate_employee,
)
from app.modules.contractors.models import ComplianceStatus


def _ready_emp():
    """An employee that is ALLOWED on the 3 base dimensions (so document rules decide)."""
    return SimpleNamespace(
        id="e1",
        contractor_id="c1",
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=date(2026, 6, 1),       # within 365d window
        next_medical_at=date(2026, 12, 1),       # future
    )


def test_no_requirements_keeps_base_verdict_allowed():
    v = evaluate_employee(_ready_emp(), TODAY)
    assert v.status is ReadinessStatus.ALLOWED


def test_mandatory_missing_document_blocks():
    req = DocumentRequirement(doc_type="medical_cert", scope="employee", mandatory=True)
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], employee_docs=[], company_docs=[])
    assert v.status is ReadinessStatus.BLOCKED
    assert "document:medical_cert" in v.violations


def test_mandatory_overdue_document_blocks():
    req = DocumentRequirement(doc_type="medical_cert", scope="employee", mandatory=True)
    doc = _Doc(TODAY - timedelta(days=1), doc_type="medical_cert")
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], employee_docs=[doc])
    assert v.status is ReadinessStatus.BLOCKED
    assert "document:medical_cert" in v.violations


def test_non_mandatory_missing_document_warns():
    req = DocumentRequirement(doc_type="insurance", scope="company", mandatory=False)
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req])
    assert v.status is ReadinessStatus.WARNING
    assert "document:insurance" in v.warnings


def test_due_soon_document_warns_even_if_mandatory():
    req = DocumentRequirement(doc_type="medical_cert", scope="employee", mandatory=True)
    doc = _Doc(TODAY + timedelta(days=10), doc_type="medical_cert")
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], employee_docs=[doc])
    assert v.status is ReadinessStatus.WARNING
    assert "document:medical_cert" in v.warnings


def test_scope_routing_company_doc_does_not_satisfy_employee_rule():
    req = DocumentRequirement(doc_type="sro", scope="employee", mandatory=True)
    company_doc = _Doc(TODAY + timedelta(days=90), doc_type="sro")
    # Document is in the company pool, but the rule looks at the employee pool → MISSING → BLOCKED.
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], company_docs=[company_doc])
    assert v.status is ReadinessStatus.BLOCKED


def test_satisfied_company_rule_is_allowed():
    req = DocumentRequirement(doc_type="sro", scope="company", mandatory=True)
    company_doc = _Doc(TODAY + timedelta(days=90), doc_type="sro")
    v = evaluate_employee(_ready_emp(), TODAY, requirements=[req], company_docs=[company_doc])
    assert v.status is ReadinessStatus.ALLOWED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_contractor_document_requirements.py -v`
Expected: FAIL — `ImportError: cannot import name 'DocumentRequirement'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/domains/contractors/lifecycle.py`:

Add the import at the top (after the existing `from app.domains.shared import ...`):

```python
from app.domains.contractors.documents import requirement_status
```

Add the dataclass after `EmployeeVerdict`:

```python
@dataclass
class DocumentRequirement:
    doc_type: str
    scope: str  # "company" | "employee"
    mandatory: bool
```

Change the signature of `evaluate_employee` and add the documents fold before the final status decision:

```python
def evaluate_employee(
    emp,
    today: date,
    *,
    requirements: "list[DocumentRequirement] | tuple[DocumentRequirement, ...]" = (),
    employee_docs=(),
    company_docs=(),
) -> EmployeeVerdict:
    """Compute the readiness verdict for a contractor employee.

    The optional document dimension (requirements/employee_docs/company_docs) defaults to
    empty → the verdict is unchanged from the 3-dimension (access/training/medical) base,
    keeping all pre-existing callers and unit tests intact. Callers pass only ACTIVE,
    non-deleted documents; this pure function filters by doc_type and folds expiry only.
    """
    violations: list[str] = []
    warnings: list[str] = []

    # access: status only, no deadline
    _assess("access", emp.access_status, None, violations, warnings)

    # training: deadline = last_training_at + TRAINING_INTERVAL_DAYS
    last_training = _as_date(emp.last_training_at)
    training_deadline = (
        classify(last_training + timedelta(days=TRAINING_INTERVAL_DAYS), today)
        if last_training is not None
        else ContingentItemStatus.MISSING
    )
    _assess("training", emp.training_status, training_deadline, violations, warnings)

    # medical: explicit deadline next_medical_at
    medical_deadline = classify(_as_date(emp.next_medical_at), today)
    _assess("medical", emp.medical_status, medical_deadline, violations, warnings)

    # documents: each required type, looked up in the scope-appropriate pool
    for req in requirements:
        pool = company_docs if req.scope == "company" else employee_docs
        candidates = [d for d in pool if d.doc_type == req.doc_type]
        st = requirement_status(candidates, today)
        label = f"document:{req.doc_type}"
        if st in (ContingentItemStatus.MISSING, ContingentItemStatus.OVERDUE):
            (violations if req.mandatory else warnings).append(label)
        elif st is ContingentItemStatus.DUE_SOON:
            warnings.append(label)

    if violations:
        status = ReadinessStatus.BLOCKED
    elif warnings:
        status = ReadinessStatus.WARNING
    else:
        status = ReadinessStatus.ALLOWED
    return EmployeeVerdict(employee_id=emp.id, status=status, violations=violations, warnings=warnings)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest backend/tests/test_contractor_document_requirements.py -v`
Expected: PASS (14 passed — 7 from Task 1 + 7 here).

- [ ] **Step 5: Run the base-dimension regression**

Run: `python -m pytest backend/tests/test_contractors_lifecycle.py -v`
Expected: PASS (unchanged — defaults make documents a no-op).

- [ ] **Step 6: Commit**

```bash
git add backend/app/domains/contractors/lifecycle.py backend/tests/test_contractor_document_requirements.py
git commit -m "feat(contractors): document dimension in evaluate_employee (back-compat defaults)"
```

---

## Task 4: Service loader `evaluate_with_documents` + reroute enforce/notify

**Files:**
- Modify: `backend/app/services/contractor_admission.py`
- Test: `tests/test_contractor_admission_with_documents.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_contractor_admission_with_documents.py
"""evaluate_with_documents: tenant isolation + company/employee scope routing + gating."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.contractors.lifecycle import ReadinessStatus
from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocument,
    ContractorDocumentRequirement,
    ContractorEmployee,
    ContractorRegistry,
)

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


async def _seed_ready_employee(session, tenant_id: str) -> ContractorEmployee:
    contractor = ContractorRegistry(tenant_id=tenant_id, name="WD Contractor")
    session.add(contractor)
    await session.flush()
    emp = ContractorEmployee(
        tenant_id=tenant_id, contractor_id=contractor.id, full_name="WD Worker",
        access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID, last_training_at=NOW,
        next_medical_at=NOW + timedelta(days=200),
    )
    session.add(emp)
    await session.flush()
    return emp


@pytest.mark.asyncio
async def test_missing_mandatory_employee_doc_blocks(sessionmaker, data_factory):
    from app.services.contractor_admission import evaluate_with_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        emp = await _seed_ready_employee(session, tid)
        session.add(ContractorDocumentRequirement(
            tenant_id=tid, doc_type="medical_cert", scope="employee", mandatory=True,
        ))
        await session.commit()
        verdicts = await evaluate_with_documents(session, employees=[emp])

    assert verdicts[0].status is ReadinessStatus.BLOCKED
    assert "document:medical_cert" in verdicts[0].violations


@pytest.mark.asyncio
async def test_company_doc_satisfies_company_rule(sessionmaker, data_factory):
    from app.services.contractor_admission import evaluate_with_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        emp = await _seed_ready_employee(session, tid)
        session.add(ContractorDocumentRequirement(
            tenant_id=tid, doc_type="sro", scope="company", mandatory=True,
        ))
        # company-level doc: employee_id is None, same contractor
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=emp.contractor_id, doc_type="sro",
            title="СРО", valid_until=TODAY + timedelta(days=90), status="active",
        ))
        await session.commit()
        verdicts = await evaluate_with_documents(session, employees=[emp])

    assert verdicts[0].status is ReadinessStatus.ALLOWED


@pytest.mark.asyncio
async def test_inactive_document_does_not_satisfy(sessionmaker, data_factory):
    from app.services.contractor_admission import evaluate_with_documents

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        emp = await _seed_ready_employee(session, tid)
        session.add(ContractorDocumentRequirement(
            tenant_id=tid, doc_type="sro", scope="company", mandatory=True,
        ))
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=emp.contractor_id, doc_type="sro",
            title="СРО (archived)", valid_until=TODAY + timedelta(days=90), status="archived",
        ))
        await session.commit()
        verdicts = await evaluate_with_documents(session, employees=[emp])

    assert verdicts[0].status is ReadinessStatus.BLOCKED  # archived doc ignored → MISSING
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_contractor_admission_with_documents.py -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate_with_documents'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/app/services/contractor_admission.py`, update imports:

```python
from sqlalchemy import and_, or_, select
from app.modules.contractors.models import (
    ContractorDocument,
    ContractorDocumentRequirement,
    ContractorEmployee,
)
```

Add the loader functions (after `evaluate_contractor_admission`):

```python
async def _load_requirements(session: AsyncSession, tenant_ids: set[str]) -> dict[str, list[lc.DocumentRequirement]]:
    """Active document requirements grouped by tenant id."""
    rows = (await session.execute(
        select(ContractorDocumentRequirement).where(
            ContractorDocumentRequirement.tenant_id.in_(tenant_ids),
            ContractorDocumentRequirement.deleted_at.is_(None),
        )
    )).scalars().all()
    by_tenant: dict[str, list[lc.DocumentRequirement]] = {}
    for r in rows:
        by_tenant.setdefault(r.tenant_id, []).append(
            lc.DocumentRequirement(doc_type=r.doc_type, scope=r.scope, mandatory=r.mandatory)
        )
    return by_tenant


async def evaluate_with_documents(
    session: AsyncSession, *, employees: list[ContractorEmployee],
) -> list[lc.EmployeeVerdict]:
    """Canonical doc-aware verdict path: load requirements + active documents, fold them in.

    Two queries total regardless of employee count. Loads only ACTIVE, non-deleted documents;
    splits them into employee-level (employee_id set) and company-level (employee_id IS NULL)
    pools, then defers the per-rule logic to the pure ``lc.evaluate_employee``.
    """
    if not employees:
        return []
    tenant_ids = {e.tenant_id for e in employees}
    reqs_by_tenant = await _load_requirements(session, tenant_ids)

    emp_ids = [e.id for e in employees]
    contractor_ids = list({e.contractor_id for e in employees})
    docs = (await session.execute(
        select(ContractorDocument).where(
            ContractorDocument.tenant_id.in_(tenant_ids),
            ContractorDocument.deleted_at.is_(None),
            ContractorDocument.status == "active",
            or_(
                ContractorDocument.employee_id.in_(emp_ids),
                and_(
                    ContractorDocument.employee_id.is_(None),
                    ContractorDocument.contractor_id.in_(contractor_ids),
                ),
            ),
        )
    )).scalars().all()

    emp_docs: dict[str, list[ContractorDocument]] = {}
    company_docs: dict[str, list[ContractorDocument]] = {}
    for d in docs:
        if d.employee_id is not None:
            emp_docs.setdefault(d.employee_id, []).append(d)
        else:
            company_docs.setdefault(d.contractor_id, []).append(d)

    today = datetime.now(timezone.utc).date()
    return [
        lc.evaluate_employee(
            e, today,
            requirements=reqs_by_tenant.get(e.tenant_id, []),
            employee_docs=emp_docs.get(e.id, []),
            company_docs=company_docs.get(e.contractor_id, []),
        )
        for e in employees
    ]
```

Reroute `enforce_contractor_admission` — replace its per-employee evaluation loop with the loader:

```python
    # (after the missing_ids guard)
    details: list[dict[str, object]] = []
    for verdict in await evaluate_with_documents(session, employees=employees):
        if verdict.status is lc.ReadinessStatus.BLOCKED:
            details.append({"employee_id": verdict.employee_id, "violations": verdict.violations})

    if details:
        raise ValueError({"code": "requirements_not_met", "details": details})
```

Reroute `notify_readiness` — replace `lc.evaluate_employee(emp, today)` inside the loop. Load verdicts up front and zip with employees:

```python
    verdicts = await evaluate_with_documents(session, employees=employees)
    today = datetime.now(timezone.utc).date()
    outbox = OutboxService(session)
    count = 0
    by_id = {e.id: e for e in employees}
    for verdict in verdicts:
        if verdict.status is lc.ReadinessStatus.ALLOWED:
            continue
        emp = by_id[verdict.employee_id]
        event_type = (
            EventType.CONTRACTOR_READINESS_BLOCKED
            if verdict.status is lc.ReadinessStatus.BLOCKED
            else EventType.CONTRACTOR_READINESS_WARNING
        )
        await outbox.enqueue(
            tenant_id=tenant_id,
            event_type=event_type.value,
            idempotency_key=f"contractor-readiness:{emp.id}:{verdict.status.value}:{today.isoformat()}",
            payload={
                "tenant_id": tenant_id,
                "metadata": {
                    "employee_id": emp.id,
                    "contractor_id": emp.contractor_id,
                    "status": verdict.status.value,
                    "violations": verdict.violations,
                    "warnings": verdict.warnings,
                },
            },
        )
        count += 1
    return count
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_contractor_admission_with_documents.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Run admission service regression**

Run: `python -m pytest backend/tests/test_contractors_lifecycle.py backend/tests/test_contractors_deny_first.py tests/test_outbox_dispatch.py -v`
Expected: PASS (notify_readiness still emits per non-ALLOWED employee; base verdicts unchanged with no requirements seeded).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/contractor_admission.py tests/test_contractor_admission_with_documents.py
git commit -m "feat(contractors): evaluate_with_documents loader; route enforce/notify through it"
```

---

## Task 5: Requirements CRUD API

**Files:**
- Modify: `backend/app/api/routes/contractors.py`
- Test: `tests/api/test_contractor_document_requirements_api.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/api/test_contractor_document_requirements_api.py
"""Contractor document-requirement policy CRUD + isolation + feature-gate + checklist."""
from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum

BASE = "/api/v1/contractors/document-requirements"


@pytest.mark.asyncio
async def test_create_list_delete_requirement(async_client: AsyncClient, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        BASE, headers=headers,
        json={"doc_type": "sro", "scope": "company", "mandatory": True},
    )
    assert resp.status_code == status.HTTP_201_CREATED, resp.text
    req_id = resp.json()["id"]
    assert resp.json()["doc_type"] == "sro"
    assert resp.json()["scope"] == "company"
    assert resp.json()["mandatory"] is True

    listed = await async_client.get(BASE, headers=headers)
    assert listed.status_code == status.HTTP_200_OK, listed.text
    assert any(item["id"] == req_id for item in listed.json()["items"])

    deleted = await async_client.delete(f"{BASE}/{req_id}", headers=headers)
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    listed2 = await async_client.get(BASE, headers=headers)
    assert all(item["id"] != req_id for item in listed2.json()["items"])


@pytest.mark.asyncio
async def test_duplicate_requirement_returns_409(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    payload = {"doc_type": "insurance", "scope": "company", "mandatory": True}
    first = await async_client.post(BASE, headers=headers, json=payload)
    assert first.status_code == status.HTTP_201_CREATED, first.text
    dup = await async_client.post(BASE, headers=headers, json=payload)
    assert dup.status_code == status.HTTP_409_CONFLICT, dup.text


@pytest.mark.asyncio
async def test_invalid_scope_returns_422(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    resp = await async_client.post(
        BASE, headers=headers,
        json={"doc_type": "sro", "scope": "bogus", "mandatory": True},
    )
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text


@pytest.mark.asyncio
async def test_reader_cannot_create_requirement(async_client, make_auth_headers):
    headers = await make_auth_headers(RoleEnum.INSPECTOR_CONTRACTOR)
    resp = await async_client.post(
        BASE, headers=headers,
        json={"doc_type": "sro", "scope": "company", "mandatory": True},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN, resp.text
```

> **NB:** `RoleEnum.INSPECTOR_CONTRACTOR` is a read-only contractor role (in `_CONTRACTOR_READ_ROLES`
> but not `_CONTRACTOR_WRITE_ROLES`). If that exact member name differs, use any role present in the
> read list but absent from the write list to assert the 403.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_contractor_document_requirements_api.py -v`
Expected: FAIL — 404 (route not registered).

- [ ] **Step 3: Write minimal implementation**

In `backend/app/api/routes/contractors.py`, add the model import:

```python
from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorDocument,
    ContractorDocumentRequirement,
    ContractorEmployee,
    ContractorIncident,
    ContractorRegistry,
)
```

Add the loader import:

```python
from app.services.contractor_admission import (
    enforce_contractor_admission,
    evaluate_contractor_admission,
    evaluate_with_documents,
    load_document_checklist,
)
```

Add schemas near `DocType` (after the `DocType` Literal):

```python
Scope = Literal["company", "employee"]


class DocumentRequirementCreate(BaseModel):
    doc_type: DocType
    scope: Scope
    mandatory: bool = True
```

Add a body helper near `_document_body`:

```python
def _requirement_body(req: ContractorDocumentRequirement) -> dict:
    return {
        "id": req.id,
        "doc_type": req.doc_type,
        "scope": req.scope,
        "mandatory": req.mandatory,
    }
```

Add the routes (place after the document CRUD block):

```python
# ---------------------------------------------------------------------------
# Document-requirement policy (tenant-level)
# ---------------------------------------------------------------------------


@router.get("/document-requirements", dependencies=[ContractorsFeatureGate])
async def list_document_requirements(tenant: TenantDep, session: SessionDep, access: ReaderAccess) -> dict:
    rows = list((await session.execute(
        select(ContractorDocumentRequirement).where(
            ContractorDocumentRequirement.tenant_id == str(tenant.id),
            ContractorDocumentRequirement.deleted_at.is_(None),
        ).order_by(ContractorDocumentRequirement.doc_type)
    )).scalars().all())
    return {"items": [_requirement_body(r) for r in rows], "total": len(rows)}


@router.post(
    "/document-requirements",
    status_code=status.HTTP_201_CREATED,
    dependencies=[ContractorsFeatureGate],
)
async def create_document_requirement(
    payload: DocumentRequirementCreate, tenant: TenantDep, session: SessionDep, access: WriterAccess,
) -> dict:
    existing = (await session.execute(
        select(ContractorDocumentRequirement).where(
            ContractorDocumentRequirement.tenant_id == str(tenant.id),
            ContractorDocumentRequirement.doc_type == payload.doc_type,
            ContractorDocumentRequirement.scope == payload.scope,
            ContractorDocumentRequirement.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"code": "requirement_exists", "message": "Requirement already exists for this doc_type/scope"},
        )
    row = ContractorDocumentRequirement(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return _requirement_body(row)


@router.delete(
    "/document-requirements/{requirement_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
    dependencies=[ContractorsFeatureGate],
)
async def delete_document_requirement(
    requirement_id: str, tenant: TenantDep, session: SessionDep, access: WriterAccess,
):
    row = (await session.execute(
        select(ContractorDocumentRequirement).where(
            ContractorDocumentRequirement.id == requirement_id,
            ContractorDocumentRequirement.tenant_id == str(tenant.id),
            ContractorDocumentRequirement.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement not found")
    row.deleted_at = datetime.now(timezone.utc)
    await session.commit()
    return None
```

> `load_document_checklist` is imported here but implemented in Task 6 — add the import now and the
> function next; the checklist route arrives in Task 6. (If running Task 5 in isolation, temporarily
> drop `load_document_checklist` from the import until Task 6.)

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/test_contractor_document_requirements_api.py -v -k "requirement"`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/contractors.py tests/api/test_contractor_document_requirements_api.py
git commit -m "feat(contractors): document-requirement policy CRUD API (409 on dup, RBAC)"
```

---

## Task 6: Document-checklist endpoint

**Files:**
- Modify: `backend/app/services/contractor_admission.py` (add `load_document_checklist`)
- Modify: `backend/app/api/routes/contractors.py` (add route)
- Test: `tests/api/test_contractor_document_requirements_api.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_contractor_document_requirements_api.py`:

```python
from datetime import date, timedelta

from app.modules.contractors.models import ContractorDocument, ContractorEmployee, ContractorRegistry

TODAY = date.today()


async def _seed_employee(sessionmaker, data_factory) -> tuple[str, str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Chk Contractor")
        session.add(contractor)
        await session.flush()
        emp = ContractorEmployee(tenant_id=tid, contractor_id=contractor.id, full_name="Chk Worker")
        session.add(emp)
        await session.commit()
        return tid, str(contractor.id), str(emp.id)


@pytest.mark.asyncio
async def test_checklist_reports_status_and_satisfied_by(async_client, sessionmaker, data_factory, make_auth_headers):
    tid, contractor_id, emp_id = await _seed_employee(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    # one company rule (satisfied) + one employee rule (missing)
    await async_client.post(BASE, headers=headers, json={"doc_type": "sro", "scope": "company", "mandatory": True})
    await async_client.post(BASE, headers=headers, json={"doc_type": "medical_cert", "scope": "employee", "mandatory": True})

    # satisfying company document
    async with sessionmaker() as session:
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=contractor_id, doc_type="sro", title="СРО",
            valid_until=TODAY + timedelta(days=90), status="active",
        ))
        await session.commit()

    resp = await async_client.get(f"/api/v1/contractors/employees/{emp_id}/document-checklist", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    items = {i["doc_type"]: i for i in resp.json()["items"]}
    assert items["sro"]["status"] == "ok"
    assert items["sro"]["satisfied_by"] is not None
    assert items["medical_cert"]["status"] == "missing"
    assert items["medical_cert"]["satisfied_by"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_contractor_document_requirements_api.py::test_checklist_reports_status_and_satisfied_by -v`
Expected: FAIL — 404 (route not registered) / ImportError for `load_document_checklist`.

- [ ] **Step 3: Implement the loader**

In `backend/app/services/contractor_admission.py`, add imports and the function:

```python
from app.domains.contractors.documents import best_document, document_expiry_status, requirement_status


async def load_document_checklist(
    session: AsyncSession, *, employee: ContractorEmployee,
) -> list[dict[str, object]]:
    """Per-requirement collection status for one employee (feeds the guided-collection UI).

    Returns one item per active tenant requirement: its status (ok/due_soon/overdue/missing)
    and the best satisfying document, if any.
    """
    today = datetime.now(timezone.utc).date()
    reqs_by_tenant = await _load_requirements(session, {employee.tenant_id})
    requirements = reqs_by_tenant.get(employee.tenant_id, [])

    docs = (await session.execute(
        select(ContractorDocument).where(
            ContractorDocument.tenant_id == employee.tenant_id,
            ContractorDocument.deleted_at.is_(None),
            ContractorDocument.status == "active",
            or_(
                ContractorDocument.employee_id == employee.id,
                and_(
                    ContractorDocument.employee_id.is_(None),
                    ContractorDocument.contractor_id == employee.contractor_id,
                ),
            ),
        )
    )).scalars().all()
    employee_docs = [d for d in docs if d.employee_id is not None]
    company_docs = [d for d in docs if d.employee_id is None]

    items: list[dict[str, object]] = []
    for req in requirements:
        pool = company_docs if req.scope == "company" else employee_docs
        candidates = [d for d in pool if d.doc_type == req.doc_type]
        st = requirement_status(candidates, today)
        best = best_document(candidates, today)
        items.append({
            "doc_type": req.doc_type,
            "scope": req.scope,
            "mandatory": req.mandatory,
            "status": st.value,
            "satisfied_by": (
                {"document_id": best.id,
                 "valid_until": best.valid_until.isoformat() if best.valid_until else None}
                if best is not None else None
            ),
        })
    return items
```

- [ ] **Step 4: Add the route**

In `backend/app/api/routes/contractors.py`, add after the admission endpoints (near `get_employee_readiness`):

```python
@router.get(
    "/employees/{employee_id}/document-checklist",
    dependencies=[ContractorsFeatureGate],
)
async def get_employee_document_checklist(
    employee_id: str, tenant: TenantDep, session: SessionDep, access: ReaderAccess,
) -> dict:
    """Per-requirement document collection status for a contractor employee (advisory)."""
    row = await _fetch_employee(session, tenant, employee_id)
    access.ensure_abac(contractor_id=row.contractor_id, action="read contractors")
    items = await load_document_checklist(session, employee=row)
    return {"employee_id": employee_id, "items": items}
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/api/test_contractor_document_requirements_api.py -v`
Expected: PASS (all requirement + checklist tests).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/contractor_admission.py backend/app/api/routes/contractors.py tests/api/test_contractor_document_requirements_api.py
git commit -m "feat(contractors): document-checklist endpoint (wizard deliverable)"
```

---

## Task 7: Wire `/admit` + `/readiness` through the loader (e2e gating)

**Files:**
- Modify: `backend/app/api/routes/contractors.py`
- Test: `tests/api/test_contractor_document_requirements_api.py` (append)

- [ ] **Step 1: Write the failing test**

Append to `tests/api/test_contractor_document_requirements_api.py`:

```python
from app.modules.contractors.models import ComplianceStatus
from datetime import datetime, timezone


async def _seed_ready_employee_db(sessionmaker, data_factory) -> tuple[str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Admit Contractor")
        session.add(contractor)
        await session.flush()
        now = datetime.now(timezone.utc)
        emp = ContractorEmployee(
            tenant_id=tid, contractor_id=contractor.id, full_name="Admit Worker",
            access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
            medical_status=ComplianceStatus.VALID, last_training_at=now,
            next_medical_at=now + timedelta(days=200),
        )
        session.add(emp)
        await session.commit()
        return tid, str(emp.id)


@pytest.mark.asyncio
async def test_admit_blocked_by_missing_mandatory_document(async_client, sessionmaker, data_factory, make_auth_headers):
    _tid, emp_id = await _seed_ready_employee_db(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    # base 3 dims are clear; add a mandatory employee document rule with no document
    await async_client.post(BASE, headers=headers, json={"doc_type": "medical_cert", "scope": "employee", "mandatory": True})

    resp = await async_client.post(f"/api/v1/contractors/employees/{emp_id}/admit", headers=headers)
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == "requirements_not_met"
    violations = [v for d in detail["details"] for v in d["violations"]]
    assert "document:medical_cert" in violations


@pytest.mark.asyncio
async def test_admit_passes_when_document_present(async_client, sessionmaker, data_factory, make_auth_headers):
    tid, emp_id = await _seed_ready_employee_db(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    await async_client.post(BASE, headers=headers, json={"doc_type": "medical_cert", "scope": "employee", "mandatory": True})
    async with sessionmaker() as session:
        # fetch contractor_id for the employee
        from sqlalchemy import select as _select
        emp = (await session.execute(_select(ContractorEmployee).where(ContractorEmployee.id == emp_id))).scalar_one()
        session.add(ContractorDocument(
            tenant_id=tid, contractor_id=emp.contractor_id, employee_id=emp_id,
            doc_type="medical_cert", title="Медзаключение",
            valid_until=TODAY + timedelta(days=90), status="active",
        ))
        await session.commit()

    resp = await async_client.post(f"/api/v1/contractors/employees/{emp_id}/admit", headers=headers)
    assert resp.status_code == status.HTTP_200_OK, resp.text
    assert resp.json()["status"] == "allowed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/api/test_contractor_document_requirements_api.py::test_admit_blocked_by_missing_mandatory_document -v`
Expected: FAIL — admit returns 200 (documents not yet consulted in the success/readiness re-evaluation; enforce already uses the loader from Task 4, so this may already 409 — if so, confirm, but the readiness/success body still needs the loader).

- [ ] **Step 3: Implement**

In `backend/app/api/routes/contractors.py`:

`get_employee_readiness` — replace the verdict line:

```python
    verdict = (await evaluate_with_documents(session, employees=[row]))[0]
    return _verdict_body(verdict)
```

`admit_contractor_employee` — replace the success-body line:

```python
    # enforce is read-only, so ``row`` is still fresh; re-evaluate (incl. documents) for the body.
    return _verdict_body((await evaluate_with_documents(session, employees=[row]))[0])
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/api/test_contractor_document_requirements_api.py -v`
Expected: PASS (all, incl. both admit e2e tests).

- [ ] **Step 5: Run the contractors API regression**

Run: `python -m pytest tests/api/test_contractor_documents_api.py backend/tests/test_contractors_access_parity.py -v`
Expected: PASS (existing behavior unaffected when no requirements seeded).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/routes/contractors.py tests/api/test_contractor_document_requirements_api.py
git commit -m "feat(contractors): admit/readiness consult document requirements (e2e gate)"
```

---

## Task 8: Projection fills `missing_docs_count`

**Files:**
- Modify: `backend/app/modules/projections/services.py`
- Test: `backend/tests/test_contractor_readiness_projection_documents.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_contractor_readiness_projection_documents.py
"""Projection fills missing_docs_count from document-requirement violations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.contractors.models import (
    ComplianceStatus, ContractorDocumentRequirement, ContractorEmployee, ContractorRegistry,
)
from app.modules.projections.models import ContractorReadinessReadModel
from app.modules.projections.services import ContractorReadinessProjectionService
from sqlalchemy import select

NOW = datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_missing_docs_count_reflects_document_violations(sessionmaker, data_factory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        contractor = ContractorRegistry(tenant_id=tid, name="Proj Contractor")
        session.add(contractor)
        await session.flush()
        session.add(ContractorEmployee(
            tenant_id=tid, contractor_id=contractor.id, full_name="Proj Worker",
            access_status=ComplianceStatus.VALID, training_status=ComplianceStatus.VALID,
            medical_status=ComplianceStatus.VALID, last_training_at=NOW,
            next_medical_at=NOW + timedelta(days=200),
        ))
        session.add(ContractorDocumentRequirement(
            tenant_id=tid, doc_type="medical_cert", scope="employee", mandatory=True,
        ))
        await session.commit()

        await ContractorReadinessProjectionService(session, tid).rebuild()

        row = (await session.execute(
            select(ContractorReadinessReadModel).where(
                ContractorReadinessReadModel.tenant_id == tid,
                ContractorReadinessReadModel.contractor_id == contractor.id,
            )
        )).scalar_one()
        assert row.missing_docs_count == 1
        assert row.readiness_status == "blocked"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest backend/tests/test_contractor_readiness_projection_documents.py -v`
Expected: FAIL — `missing_docs_count == 0` (placeholder).

- [ ] **Step 3: Implement**

In `backend/app/modules/projections/services.py`:

Replace the import:

```python
from app.services.contractor_admission import evaluate_with_documents
```

In `ContractorReadinessProjectionService.rebuild`, compute all verdicts once (after `employees_by_contractor` is built) and index by employee id:

```python
        all_verdicts = await evaluate_with_documents(self.session, employees=list(employees))
        verdict_by_emp = {v.employee_id: v for v in all_verdicts}
```

Replace the per-registry verdict line:

```python
            verdicts = [verdict_by_emp[e.id] for e in contractor_employees]
```

Replace the `missing_docs_count` placeholder line:

```python
            row.missing_docs_count = sum(
                1 for v in verdicts for viol in v.violations if viol.startswith("document:")
            )
```

(`overdue_items_count = sum(len(v.violations) for v in verdicts)` already includes document violations — leave it.)

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_contractor_readiness_projection_documents.py -v`
Expected: PASS.

- [ ] **Step 5: Run projection regression**

Run: `python -m pytest backend/tests -k "projection" -v`
Expected: PASS (existing contractor-readiness projection tests still green; with no requirements, `missing_docs_count` is 0 as before).

- [ ] **Step 6: Commit**

```bash
git add backend/app/modules/projections/services.py backend/tests/test_contractor_readiness_projection_documents.py
git commit -m "feat(contractors): projection fills missing_docs_count from document violations"
```

---

## Task 9: Demo-seed requirements

**Files:**
- Modify: `backend/app/services/demo_bootstrap.py`
- Test: `tests/test_demo_bootstrap_contractor_requirements.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_demo_bootstrap_contractor_requirements.py
"""Demo bootstrap seeds tenant document requirements (sro/company, medical_cert/employee)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.modules.contractors.models import ContractorDocumentRequirement


@pytest.mark.asyncio
async def test_seed_requirements_idempotent(sessionmaker, data_factory):
    from app.services.demo_bootstrap import _seed_contractor_requirements

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await _seed_contractor_requirements(session, tid)
        await session.commit()
        # second call must not duplicate
        await _seed_contractor_requirements(session, tid)
        await session.commit()

        rows = (await session.execute(
            select(ContractorDocumentRequirement).where(
                ContractorDocumentRequirement.tenant_id == tid,
                ContractorDocumentRequirement.deleted_at.is_(None),
            )
        )).scalars().all()

    pairs = {(r.doc_type, r.scope) for r in rows}
    assert ("sro", "company") in pairs
    assert ("medical_cert", "employee") in pairs
    assert len(rows) == 2  # idempotent — no duplicates
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_demo_bootstrap_contractor_requirements.py -v`
Expected: FAIL — `ImportError: cannot import name '_seed_contractor_requirements'`.

- [ ] **Step 3: Implement**

In `backend/app/services/demo_bootstrap.py`, add the import for the model (extend the existing line):

```python
from app.modules.contractors.models import (
    ComplianceStatus, ContractorDocument, ContractorDocumentRequirement,
    ContractorEmployee, ContractorRegistry,
)
```

Add the helper near `_seed_contractor_documents`:

```python
async def _seed_contractor_requirements(session, tenant_db_id: str) -> None:
    """Seed 2 admission document requirements (idempotent on tenant+doc_type+scope)."""
    wanted = [("sro", "company"), ("medical_cert", "employee")]
    for doc_type, scope in wanted:
        existing = (await session.execute(
            select(ContractorDocumentRequirement).where(
                ContractorDocumentRequirement.tenant_id == tenant_db_id,
                ContractorDocumentRequirement.doc_type == doc_type,
                ContractorDocumentRequirement.scope == scope,
                ContractorDocumentRequirement.deleted_at.is_(None),
            )
        )).scalar_one_or_none()
        if existing is None:
            session.add(ContractorDocumentRequirement(
                tenant_id=tenant_db_id, doc_type=doc_type, scope=scope, mandatory=True,
            ))
```

Call it inside the demo contractor block (right after `_seed_contractor_documents(...)` at line ~223):

```python
            await _seed_contractor_documents(session, tenant_db_id, contractor.id, ready_emp.id)
            await _seed_contractor_requirements(session, tenant_db_id)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_demo_bootstrap_contractor_requirements.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/demo_bootstrap.py tests/test_demo_bootstrap_contractor_requirements.py
git commit -m "feat(contractors): demo-seed 2 admission document requirements"
```

---

## Final: Full contour cohort + regression

- [ ] **Step 1: Run the Срез-3 cohort + adjacent regression**

```
$env:PYTHONPATH="backend"; & .\.venv\Scripts\python.exe -m pytest `
  backend/tests/test_contractor_document_requirements.py `
  backend/tests/test_con02_contractor_document_requirements_migration.py `
  backend/tests/test_contractor_readiness_projection_documents.py `
  tests/test_contractor_admission_with_documents.py `
  tests/api/test_contractor_document_requirements_api.py `
  tests/test_demo_bootstrap_contractor_requirements.py `
  backend/tests/test_contractors_lifecycle.py `
  backend/tests/test_contractors_access_parity.py `
  backend/tests/test_contractors_deny_first.py `
  tests/api/test_contractor_documents_api.py `
  tests/test_outbox_dispatch.py `
  -p no:xdist --timeout=300 > _t_srez3.txt 2>&1; "EXIT=$LASTEXITCODE"
```
Expected: EXIT=0; all passed. (Read `_t_srez3.txt` tail for the `N passed` summary.)

- [ ] **Step 2: Clean up temp file**

```bash
rm -f _t_srez3.txt
```

- [ ] **Step 3: Update the handoff report**

Prepend a "Last Agent Handoff (2026-06-10, Подрядчики Срез-3)" section to `AI_IMPLEMENTATION_REPORT.md` documenting: branch, 9 tasks/commits, the document→verdict gate, `missing_docs_count` now filled, checklist API, anti-grabli adherence (VARCHAR/no-enum, no cross-base FK, additive con02), test evidence, and the e2e safety invariant. Commit.

---

## Self-Review (completed by author)

**Spec coverage:** §2 table → Task 2; §3.1 `requirement_status` → Task 1; §3.2 `evaluate_employee` → Task 3; §4 loader/reroute → Task 4; §5 requirements CRUD → Task 5; §5 checklist → Task 6; §5 admit/readiness → Task 7; §6 projection → Task 8; §7 migration → Task 2; §8 seed → Task 9; §9 tests distributed across tasks; §10 invariant → Task 7. **All sections mapped.**

**Type consistency:** `DocumentRequirement(doc_type, scope, mandatory)`, `evaluate_with_documents(session, *, employees)`, `load_document_checklist(session, *, employee)`, `requirement_status(candidates, today)`, `best_document(candidates, today)`, `_requirement_body`, status strings `ok/due_soon/overdue/missing` (`ContingentItemStatus.value`), violation label `document:<doc_type>` — used identically across Tasks 1, 3, 4, 6, 7, 8.

**Placeholder scan:** No TBD/TODO; every code step shows full code; commands have expected output.

**Verification points (resolved during plan authoring):**
- `RoleEnum.INSPECTOR_CONTRACTOR = "inspector_contractor"` confirmed present (`models.py:217`); it is in `_CONTRACTOR_READ_ROLES` but not `_CONTRACTOR_WRITE_ROLES` → valid 403 fixture (Task 5).
- `ContingentItemStatus` values confirmed `ok/due_soon/overdue/missing` (`shared.py:15-18`) → checklist `status` via `.value` is correct, no mapping dict needed.
