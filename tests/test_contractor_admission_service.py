"""Tests for contractor_admission service (Task 3).

Fixture name: ``sessionmaker`` / ``data_factory`` — same as test_medical_service.py.
Pattern: async with sessionmaker() as session → seed → commit → call service.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.contractors.models import (
    ComplianceStatus,
    ContractorEmployee,
    ContractorRegistry,
)
from app.services.contractor_admission import (
    enforce_contractor_admission,
    evaluate_contractor_admission,
)

# ---------------------------------------------------------------------------
# Helpers
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
        last_training_at=now,  # training deadline ≈ today + 365 days → OK → ALLOWED
        next_medical_at=now + timedelta(days=200),
    )


def _make_stale_employee(tenant_id: str, contractor_id: str) -> ContractorEmployee:
    """Stale employee: medical_status=VALID but next_medical_at=yesterday → BLOCKED."""
    now = _now_utc()
    return ContractorEmployee(
        tenant_id=tenant_id,
        contractor_id=contractor_id,
        full_name="Stale Worker",
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=now,
        next_medical_at=now - timedelta(days=1),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_returns_verdicts(sessionmaker, data_factory):
    """evaluate_contractor_admission returns ALLOWED for ready, BLOCKED for stale."""
    from app.domains.contractors.lifecycle import ReadinessStatus

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        ready = _make_ready_employee(tid, registry.id)
        stale = _make_stale_employee(tid, registry.id)
        session.add(ready)
        session.add(stale)
        await session.commit()

        verdicts = evaluate_contractor_admission(employees=[ready, stale])

    assert len(verdicts) == 2

    ready_verdict = next(v for v in verdicts if v.employee_id == ready.id)
    stale_verdict = next(v for v in verdicts if v.employee_id == stale.id)

    assert (
        ready_verdict.status is ReadinessStatus.ALLOWED
    ), f"Expected ALLOWED, got {ready_verdict.status}; violations={ready_verdict.violations}"
    assert (
        stale_verdict.status is ReadinessStatus.BLOCKED
    ), f"Expected BLOCKED, got {stale_verdict.status}"
    assert "medical" in stale_verdict.violations


@pytest.mark.asyncio
async def test_enforce_raises_requirements_not_met(sessionmaker, data_factory):
    """enforce_contractor_admission raises ValueError for BLOCKED employees."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        stale = _make_stale_employee(tid, registry.id)
        session.add(stale)
        await session.commit()

        with pytest.raises(ValueError) as exc_info:
            await enforce_contractor_admission(
                session,
                tenant_scope=(tid,),
                employee_ids=[stale.id],
            )

    err = exc_info.value.args[0]
    assert err["code"] == "requirements_not_met"
    assert len(err["details"]) >= 1
    detail = err["details"][0]
    assert detail["employee_id"] == stale.id
    assert "medical" in detail["violations"]


@pytest.mark.asyncio
async def test_enforce_passes_for_ready(sessionmaker, data_factory):
    """enforce_contractor_admission does NOT raise for a fully-ready employee."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        ready = _make_ready_employee(tid, registry.id)
        session.add(ready)
        await session.commit()

        # Must not raise
        await enforce_contractor_admission(
            session,
            tenant_scope=(tid,),
            employee_ids=[ready.id],
        )


@pytest.mark.asyncio
async def test_enforce_empty_ids_is_noop(sessionmaker, data_factory):
    """enforce_contractor_admission with no ids returns cleanly (no raise)."""
    async with sessionmaker() as session:
        await enforce_contractor_admission(
            session,
            tenant_scope=("any-tenant",),
            employee_ids=[],
        )


@pytest.mark.asyncio
async def test_enforce_raises_for_unknown_id(sessionmaker, data_factory):
    """A requested id absent within tenant scope must block, not silently pass."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        with pytest.raises(ValueError) as exc_info:
            await enforce_contractor_admission(
                session,
                tenant_scope=(tid,),
                employee_ids=["does-not-exist"],
            )

    err = exc_info.value.args[0]
    assert err["code"] == "employees_not_found"
    assert "does-not-exist" in err["details"]


@pytest.mark.asyncio
async def test_notify_readiness_enqueues_for_non_allowed(sessionmaker, data_factory):
    """notify_readiness enqueues events only for non-ALLOWED (BLOCKED) employees."""
    from app.services.contractor_admission import notify_readiness

    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        tid = str(tenant.id)

        registry = _make_registry(tid)
        session.add(registry)
        await session.flush()

        ready = _make_ready_employee(tid, registry.id)  # ALLOWED — must be skipped
        stale = _make_stale_employee(tid, registry.id)  # BLOCKED — must be enqueued
        session.add(ready)
        session.add(stale)
        await session.commit()

        count = await notify_readiness(session, tenant_id=tid)
        await session.commit()

    assert count == 1, f"Expected 1 event (stale/BLOCKED only), got {count}"
