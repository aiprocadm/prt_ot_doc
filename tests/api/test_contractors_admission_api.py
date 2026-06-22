"""Task 4 — contractor admission gate + advisory readiness API tests.

Covers:
  POST /api/v1/contractors/employees/{id}/admit
    - stale employee (medical valid but deadline past) → 409 requirements_not_met
    - ready employee (all valid, fresh deadlines) → 200 allowed

  GET /api/v1/contractors/employees/{id}/readiness
    - ready employee → 200 allowed
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.models import RoleEnum
from app.modules.contractors.models import ComplianceStatus, ContractorEmployee, ContractorRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime.now(timezone.utc)
_PAST = _NOW - timedelta(days=10)
_SOON = _NOW + timedelta(days=10)  # within the 30-day warning window → DUE_SOON
_FUTURE = _NOW + timedelta(days=200)


async def _seed_employee(
    sessionmaker,
    data_factory,
    *,
    access_status: ComplianceStatus = ComplianceStatus.VALID,
    training_status: ComplianceStatus = ComplianceStatus.VALID,
    medical_status: ComplianceStatus = ComplianceStatus.VALID,
    last_training_at: datetime | None = None,
    next_medical_at: datetime | None = None,
) -> tuple[str, str]:
    """Return (contractor_id, employee_id)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        contractor = ContractorRegistry(
            tenant_id=str(tenant.id),
            name="Seed Contractor",
        )
        session.add(contractor)
        await session.flush()

        emp = ContractorEmployee(
            tenant_id=str(tenant.id),
            contractor_id=str(contractor.id),
            full_name="Test Worker",
            access_status=access_status,
            training_status=training_status,
            medical_status=medical_status,
            last_training_at=last_training_at,
            next_medical_at=next_medical_at,
        )
        session.add(emp)
        await session.commit()
        return str(contractor.id), str(emp.id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admit_stale_employee_returns_409(
    async_client: AsyncClient,
    sessionmaker,
    data_factory,
    make_auth_headers,
) -> None:
    """A medical-valid employee whose next_medical_at is in the past is BLOCKED → 409."""
    contractor_id, emp_id = await _seed_employee(
        sessionmaker,
        data_factory,
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=_NOW,
        next_medical_at=_PAST,  # overdue → BLOCKED
    )
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        f"/api/v1/contractors/employees/{emp_id}/admit",
        headers=headers,
    )
    assert resp.status_code == status.HTTP_409_CONFLICT, resp.text
    body = resp.json()
    detail = body.get("detail", body)
    assert detail["code"] == "requirements_not_met"
    assert detail["details"][0]["employee_id"] == emp_id


@pytest.mark.asyncio
async def test_admit_ready_employee_returns_200(
    async_client: AsyncClient,
    sessionmaker,
    data_factory,
    make_auth_headers,
) -> None:
    """A fully-ready employee passes admission → 200 with status allowed."""
    _contractor_id, emp_id = await _seed_employee(
        sessionmaker,
        data_factory,
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=_NOW,
        next_medical_at=_FUTURE,
    )
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        f"/api/v1/contractors/employees/{emp_id}/admit",
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["status"] == "allowed"
    assert body["employee_id"] == emp_id


@pytest.mark.asyncio
async def test_admit_warning_employee_returns_200_warning(
    async_client: AsyncClient,
    sessionmaker,
    data_factory,
    make_auth_headers,
) -> None:
    """A non-blocked employee with a due-soon deadline admits with 200 + status warning."""
    _contractor_id, emp_id = await _seed_employee(
        sessionmaker,
        data_factory,
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=_NOW,
        next_medical_at=_SOON,  # due soon → WARNING, not blocked
    )
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.post(
        f"/api/v1/contractors/employees/{emp_id}/admit",
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["status"] == "warning"
    assert "medical" in body["warnings"]


@pytest.mark.asyncio
async def test_readiness_ready_employee_returns_200(
    async_client: AsyncClient,
    sessionmaker,
    data_factory,
    make_auth_headers,
) -> None:
    """GET readiness for a ready employee returns 200 with status allowed."""
    _contractor_id, emp_id = await _seed_employee(
        sessionmaker,
        data_factory,
        access_status=ComplianceStatus.VALID,
        training_status=ComplianceStatus.VALID,
        medical_status=ComplianceStatus.VALID,
        last_training_at=_NOW,
        next_medical_at=_FUTURE,
    )
    headers = await make_auth_headers(RoleEnum.ADMIN)

    resp = await async_client.get(
        f"/api/v1/contractors/employees/{emp_id}/readiness",
        headers=headers,
    )
    assert resp.status_code == status.HTTP_200_OK, resp.text
    body = resp.json()
    assert body["status"] == "allowed"
    assert body["employee_id"] == emp_id
