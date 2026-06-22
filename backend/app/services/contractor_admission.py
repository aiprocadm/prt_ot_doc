"""Contractor admission service.

Wraps the pure lifecycle rules from ``app.domains.contractors.lifecycle``
with DB access, mirroring the pattern of ``person_admission.py``.

Public API
----------
evaluate_contractor_admission  — pure compute over already-loaded employees (3 base dims)
evaluate_with_documents        — canonical doc-aware verdict path (loads requirements + docs)
load_document_checklist        — per-requirement collection status for one employee
enforce_contractor_admission   — load + evaluate (doc-aware) + raise for BLOCKED employees
notify_readiness               — load + evaluate (doc-aware) + enqueue outbox for non-ALLOWED
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contractors import lifecycle as lc
from app.domains.contractors.documents import best_document, requirement_status
from app.modules.contractors.models import (
    ContractorDocument,
    ContractorDocumentRequirement,
    ContractorEmployee,
)
from app.services.events import EventType
from app.services.outbox import OutboxService


def evaluate_contractor_admission(
    *,
    employees: list[ContractorEmployee],
) -> list[lc.EmployeeVerdict]:
    """Pure compute over already-loaded employees. No DB queries, no raise.

    Uses today's UTC date from the wall clock. Callers pass an
    already-tenant-filtered list of employees.
    """
    today = datetime.now(timezone.utc).date()
    return [lc.evaluate_employee(emp, today) for emp in employees]


async def _load_requirements(
    session: AsyncSession, tenant_ids: set[str]
) -> dict[str, list[lc.DocumentRequirement]]:
    """Active document requirements grouped by tenant id."""
    rows = (
        (
            await session.execute(
                select(ContractorDocumentRequirement).where(
                    ContractorDocumentRequirement.tenant_id.in_(tenant_ids),
                    ContractorDocumentRequirement.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    by_tenant: dict[str, list[lc.DocumentRequirement]] = {}
    for r in rows:
        by_tenant.setdefault(r.tenant_id, []).append(
            lc.DocumentRequirement(doc_type=r.doc_type, scope=r.scope, mandatory=r.mandatory)
        )
    return by_tenant


async def evaluate_with_documents(
    session: AsyncSession,
    *,
    employees: list[ContractorEmployee],
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
    docs = (
        (
            await session.execute(
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
            )
        )
        .scalars()
        .all()
    )

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
            e,
            today,
            requirements=reqs_by_tenant.get(e.tenant_id, []),
            employee_docs=emp_docs.get(e.id, []),
            company_docs=company_docs.get(e.contractor_id, []),
        )
        for e in employees
    ]


async def load_document_checklist(
    session: AsyncSession,
    *,
    employee: ContractorEmployee,
) -> list[dict[str, object]]:
    """Per-requirement collection status for one employee (feeds the guided-collection UI).

    Returns one item per active tenant requirement: its status (ok/due_soon/overdue/missing)
    and the best satisfying document, if any. Among equal-status candidates ``best_document``
    keeps input (query) order — which document is reported is not otherwise specified.
    """
    today = datetime.now(timezone.utc).date()
    reqs_by_tenant = await _load_requirements(session, {employee.tenant_id})
    requirements = reqs_by_tenant.get(employee.tenant_id, [])

    docs = (
        (
            await session.execute(
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
            )
        )
        .scalars()
        .all()
    )
    employee_docs = [d for d in docs if d.employee_id is not None]
    company_docs = [d for d in docs if d.employee_id is None]

    items: list[dict[str, object]] = []
    for req in requirements:
        pool = company_docs if req.scope == "company" else employee_docs
        candidates = [d for d in pool if d.doc_type == req.doc_type]
        st = requirement_status(candidates, today)
        best = best_document(candidates, today)
        items.append(
            {
                "doc_type": req.doc_type,
                "scope": req.scope,
                "mandatory": req.mandatory,
                "status": st.value,
                "satisfied_by": (
                    {
                        "document_id": best.id,
                        "valid_until": best.valid_until.isoformat() if best.valid_until else None,
                    }
                    if best is not None
                    else None
                ),
            }
        )
    return items


async def enforce_contractor_admission(
    session: AsyncSession,
    *,
    tenant_scope: tuple[str, ...],
    employee_ids: list[str],
) -> None:
    """Load employees by id within tenant_scope, evaluate, raise for BLOCKED.

    Raises:
        ValueError: ``{"code": "employees_not_found", "details": [<id>, ...]}``
            when any requested id is absent within the tenant scope — the gate
            must never silently pass an employee it could not verify.
        ValueError: ``{"code": "requirements_not_met", "details": [...]}``
            where each detail entry is ``{"employee_id": ..., "violations": [...]}``.
            Only BLOCKED employees are listed.
    """
    if not employee_ids:
        return

    stmt = select(ContractorEmployee).where(
        ContractorEmployee.id.in_(employee_ids),
        ContractorEmployee.tenant_id.in_(tenant_scope),
        ContractorEmployee.deleted_at.is_(None),
    )
    employees = list((await session.execute(stmt)).scalars().all())

    # Defense in depth: a not-found id must block, never silently pass the gate.
    found_ids = {emp.id for emp in employees}
    missing_ids = [eid for eid in employee_ids if eid not in found_ids]
    if missing_ids:
        raise ValueError({"code": "employees_not_found", "details": missing_ids})

    details: list[dict[str, object]] = []
    for verdict in await evaluate_with_documents(session, employees=employees):
        if verdict.status is lc.ReadinessStatus.BLOCKED:
            details.append({"employee_id": verdict.employee_id, "violations": verdict.violations})

    if details:
        raise ValueError({"code": "requirements_not_met", "details": details})


async def notify_readiness(
    session: AsyncSession,
    *,
    tenant_id: str,
) -> int:
    """Load all non-deleted employees of the tenant, evaluate, enqueue outbox events.

    Enqueues:
      - ``contractor.readiness_blocked`` for each BLOCKED employee
      - ``contractor.readiness_warning`` for each WARNING employee

    Idempotent per employee per UTC date via the idempotency key.

    Returns the count of events enqueued.
    """
    stmt = select(ContractorEmployee).where(
        ContractorEmployee.tenant_id == tenant_id,
        ContractorEmployee.deleted_at.is_(None),
    )
    employees = list((await session.execute(stmt)).scalars().all())

    verdicts = await evaluate_with_documents(session, employees=employees)
    today = datetime.now(timezone.utc).date()
    outbox = OutboxService(session)
    count = 0
    by_id = {e.id: e for e in employees}

    for verdict in verdicts:
        if verdict.status is lc.ReadinessStatus.ALLOWED:
            continue
        emp = by_id[verdict.employee_id]

        if verdict.status is lc.ReadinessStatus.BLOCKED:
            event_type = EventType.CONTRACTOR_READINESS_BLOCKED
        else:
            event_type = EventType.CONTRACTOR_READINESS_WARNING

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
