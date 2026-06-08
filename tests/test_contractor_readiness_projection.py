"""Tests for ContractorReadinessProjectionService (Task 5).

TDD: this test was written BEFORE rebuild was rewritten.
The stub only filled active_packages_count; workers_total was always 0.

Fixture pattern: sessionmaker / data_factory — same as test_contractor_admission_service.py.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorEmployee,
    ContractorRegistry,
)
from app.modules.projections.models import ContractorReadinessReadModel
from app.modules.projections.services import ContractorReadinessProjectionService
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Helpers (mirrored from test_contractor_admission_service.py)
# ---------------------------------------------------------------------------

def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_registry(tenant_id: str) -> ContractorRegistry:
    return ContractorRegistry(
        tenant_id=tenant_id,
        name="Test Contractor Co.",
    )


def _make_ready_employee(tenant_id: str, contractor_id: str) -> ContractorEmployee:
    """Fully ready employee: all VALID, training fresh, medical expires in 200 days."""
    now = _now_utc()
    return ContractorEmployee(
        tenant_id=tenant_id,
        contractor_id=contractor_id,
        full_name="Ready Worker",
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=now,
        next_medical_at=now + timedelta(days=200),
    )


def _make_blocked_employee(tenant_id: str, contractor_id: str) -> ContractorEmployee:
    """Blocked employee: medical_status VALID but next_medical_at yesterday → BLOCKED."""
    now = _now_utc()
    return ContractorEmployee(
        tenant_id=tenant_id,
        contractor_id=contractor_id,
        full_name="Blocked Worker",
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=now,
        next_medical_at=now - timedelta(days=1),
    )


def _make_warning_employee(tenant_id: str, contractor_id: str) -> ContractorEmployee:
    """Warning employee: all VALID but next_medical_at due soon (within 30d) → WARNING."""
    now = _now_utc()
    return ContractorEmployee(
        tenant_id=tenant_id,
        contractor_id=contractor_id,
        full_name="Warning Worker",
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=now,
        next_medical_at=now + timedelta(days=10),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_readiness_projection_fills_worker_columns(sessionmaker, data_factory):
    """rebuild() correctly computes worker counts from employee verdicts."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        ready = _make_ready_employee(tid, registry.id)
        blocked = _make_blocked_employee(tid, registry.id)
        session.add(ready)
        session.add(blocked)
        await session.commit()

        svc = ContractorReadinessProjectionService(session, tid)
        count = await svc.rebuild()

    assert count >= 1, f"rebuild() should return >= 1 rows written, got {count}"

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == tid,
                    ContractorReadinessReadModel.contractor_id == registry.id,
                )
            )
        ).scalar_one_or_none()

    assert row is not None, "ContractorReadinessReadModel row must exist after rebuild()"
    assert row.workers_total == 2, f"workers_total should be 2, got {row.workers_total}"
    assert row.workers_ready == 1, f"workers_ready should be 1, got {row.workers_ready}"
    assert row.workers_blocked == 1, f"workers_blocked should be 1, got {row.workers_blocked}"
    assert row.overdue_items_count >= 1, (
        f"overdue_items_count should be >= 1 (blocked worker has >=1 violation), got {row.overdue_items_count}"
    )
    assert row.readiness_status == "blocked", (
        f"readiness_status should be 'blocked' (any BLOCKED → blocked), got {row.readiness_status!r}"
    )


@pytest.mark.asyncio
async def test_readiness_projection_ready_when_all_clear(sessionmaker, data_factory):
    """rebuild() sets status='ready' when all workers are ALLOWED."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        ready = _make_ready_employee(tid, registry.id)
        session.add(ready)
        await session.commit()

        count = await ContractorReadinessProjectionService(session, tid).rebuild()

    assert count >= 1

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == tid,
                    ContractorReadinessReadModel.contractor_id == registry.id,
                )
            )
        ).scalar_one_or_none()

    assert row is not None
    assert row.workers_total == 1
    assert row.workers_ready == 1
    assert row.workers_blocked == 0
    assert row.readiness_status == "ready"


@pytest.mark.asyncio
async def test_readiness_projection_warning_when_due_soon(sessionmaker, data_factory):
    """rebuild() sets status='warning' when a worker has a due-soon (not overdue) deadline."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        session.add(_make_warning_employee(tid, registry.id))
        await session.commit()

        await ContractorReadinessProjectionService(session, tid).rebuild()

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == tid,
                    ContractorReadinessReadModel.contractor_id == registry.id,
                )
            )
        ).scalar_one_or_none()

    assert row is not None
    assert row.workers_total == 1
    assert row.workers_blocked == 0
    assert row.workers_ready == 0  # WARNING is not ALLOWED
    assert row.readiness_status == "warning"


@pytest.mark.asyncio
async def test_readiness_projection_no_rows_without_registry(sessionmaker, data_factory):
    """With no contractor registry for the tenant, rebuild writes 0 rows."""
    # The authoritative contractor set is the registry; no registry → nothing to project.
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)
        await session.commit()

        count = await ContractorReadinessProjectionService(session, tid).rebuild()

    assert count == 0, f"No registry → 0 rows written, got {count}"


@pytest.mark.asyncio
async def test_readiness_projection_missing_docs_stays_zero(sessionmaker, data_factory):
    """missing_docs_count is always 0 (documents are a later slice)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        blocked = _make_blocked_employee(tid, registry.id)
        session.add(blocked)
        await session.commit()

        await ContractorReadinessProjectionService(session, tid).rebuild()

    async with sessionmaker() as session:
        row = (
            await session.execute(
                select(ContractorReadinessReadModel).where(
                    ContractorReadinessReadModel.tenant_id == tid,
                    ContractorReadinessReadModel.contractor_id == registry.id,
                )
            )
        ).scalar_one_or_none()

    assert row is not None
    assert row.missing_docs_count == 0, (
        f"missing_docs_count must stay 0 (deferred to later slice), got {row.missing_docs_count}"
    )
