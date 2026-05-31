"""API contract for the prescription status lifecycle (TZ-3.4-V12-01):
FSM transitions, evidence-on-complete, admin/owner-only verification,
closed_at stamping, and PATCH no longer moving status.
"""
from __future__ import annotations

from datetime import date

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import AuditLog, PrescriptionStatus, RoleEnum


async def _seed_company_site(sessionmaker, data_factory) -> tuple[str, str]:
    """Seed tenant + company + site via the data factory (there is no HTTP
    create-company endpoint — mirrors tests/integration/test_prescriptions_api.py);
    return (company_id, site_id)."""
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(
            tenant=tenant, company=company, session=session
        )
        await session.commit()
        return company.id, site.id


async def _seed_prescription(async_client, headers, company_id: str, site_id: str) -> str:
    """Create inspection -> prescription over HTTP; return the prescription id."""
    insp_resp = await async_client.post(
        "/api/v1/inspections",
        json={
            "company_id": company_id,
            "site_id": site_id,
            "authority": "Ростехнадзор",
            "scheduled_at": date.today().isoformat(),
        },
        headers=headers,
    )
    assert insp_resp.status_code == status.HTTP_201_CREATED, insp_resp.text
    pres_resp = await async_client.post(
        "/api/v1/prescriptions",
        json={"inspection_id": insp_resp.json()["id"], "description": "Fix guardrail"},
        headers=headers,
    )
    assert pres_resp.status_code == status.HTTP_201_CREATED, pres_resp.text
    body = pres_resp.json()
    assert body["status"] == PrescriptionStatus.OPEN.value  # create forces OPEN
    return body["id"]


async def _transition(async_client, pid, headers, to, **extra):
    return await async_client.post(
        f"/api/v1/prescriptions/{pid}/transition",
        json={"to": to, **extra},
        headers=headers,
    )


@pytest.mark.asyncio
async def test_full_lifecycle_open_to_verified(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)

    r1 = await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    assert r1.status_code == status.HTTP_200_OK, r1.text
    assert r1.json()["status"] == PrescriptionStatus.IN_PROGRESS.value

    r2 = await _transition(
        async_client, pid, headers, PrescriptionStatus.COMPLETED.value, evidence="photo#42"
    )
    assert r2.status_code == status.HTTP_200_OK, r2.text
    assert r2.json()["evidence"] == "photo#42"

    r3 = await _transition(async_client, pid, headers, PrescriptionStatus.VERIFIED.value)
    assert r3.status_code == status.HTTP_200_OK, r3.text
    assert r3.json()["status"] == PrescriptionStatus.VERIFIED.value
    assert r3.json()["closed_at"] is not None


@pytest.mark.asyncio
async def test_invalid_jump_open_to_completed_409(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)

    r = await _transition(
        async_client, pid, headers, PrescriptionStatus.COMPLETED.value, evidence="x"
    )
    assert r.status_code == status.HTTP_409_CONFLICT
    assert r.json()["detail"]["code"] == "prescription_invalid_transition"


@pytest.mark.asyncio
async def test_complete_without_evidence_422(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)

    r = await _transition(async_client, pid, headers, PrescriptionStatus.COMPLETED.value)
    assert r.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert r.json()["detail"]["code"] == "evidence_required"


@pytest.mark.asyncio
async def test_verify_forbidden_for_non_admin_403(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    admin = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, admin, company_id, site_id)
    await _transition(async_client, pid, admin, PrescriptionStatus.IN_PROGRESS.value)
    await _transition(
        async_client, pid, admin, PrescriptionStatus.COMPLETED.value, evidence="ok"
    )

    lm = await make_auth_headers(RoleEnum.LINE_MANAGER)
    r = await _transition(async_client, pid, lm, PrescriptionStatus.VERIFIED.value)
    assert r.status_code == status.HTTP_403_FORBIDDEN
    assert r.json()["detail"]["code"] == "prescription_verify_forbidden"


@pytest.mark.asyncio
async def test_failed_verification_rework_completed_to_in_progress(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)
    await _transition(
        async_client, pid, headers, PrescriptionStatus.COMPLETED.value, evidence="ok"
    )

    r = await _transition(
        async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value, note="rework"
    )
    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["status"] == PrescriptionStatus.IN_PROGRESS.value
    assert r.json()["closed_at"] is None


@pytest.mark.asyncio
async def test_cancel_stamps_closed_at(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    r = await _transition(async_client, pid, headers, PrescriptionStatus.CANCELLED.value)
    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["closed_at"] is not None


@pytest.mark.asyncio
async def test_patch_cannot_move_status(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)

    # 'status' is not a field on PrescriptionUpdate; pydantic ignores it.
    r = await async_client.patch(
        f"/api/v1/prescriptions/{pid}",
        json={"status": PrescriptionStatus.VERIFIED.value, "description": "edited"},
        headers=headers,
    )
    assert r.status_code == status.HTTP_200_OK, r.text
    assert r.json()["status"] == PrescriptionStatus.OPEN.value  # unchanged
    assert r.json()["description"] == "edited"


@pytest.mark.asyncio
async def test_transition_writes_audit_row(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid = await _seed_prescription(async_client, headers, company_id, site_id)
    await _transition(async_client, pid, headers, PrescriptionStatus.IN_PROGRESS.value)

    async with sessionmaker() as session:
        logs = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "prescription",
                    AuditLog.object_id == pid,
                    AuditLog.action == "transition",
                )
            )
        ).scalars().all()
        assert logs
