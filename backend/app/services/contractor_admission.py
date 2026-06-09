"""Contractor admission service.

Wraps the pure lifecycle rules from ``app.domains.contractors.lifecycle``
with DB access, mirroring the pattern of ``person_admission.py``.

Public API
----------
evaluate_contractor_admission  — pure compute over already-loaded employees
enforce_contractor_admission   — load + evaluate + raise for BLOCKED employees
notify_readiness               — load + evaluate + enqueue outbox events for non-ALLOWED
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.contractors import lifecycle as lc
from app.modules.contractors.models import ContractorEmployee
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

    today = datetime.now(timezone.utc).date()
    details: list[dict[str, object]] = []
    for emp in employees:
        verdict = lc.evaluate_employee(emp, today)
        if verdict.status is lc.ReadinessStatus.BLOCKED:
            details.append({"employee_id": emp.id, "violations": verdict.violations})

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

    today = datetime.now(timezone.utc).date()
    outbox = OutboxService(session)
    count = 0

    for emp in employees:
        verdict = lc.evaluate_employee(emp, today)
        if verdict.status is lc.ReadinessStatus.ALLOWED:
            continue

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
