from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.models import AuditLog, Inspection, Prescription, PrescriptionStatus, RoleEnum


@pytest.mark.anyio
async def test_prescription_crud_and_audit(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()

    inspection_payload = {
        "company_id": company.id,
        "site_id": site.id,
        "authority": "Ростехнадзор",
        "scheduled_at": date.today().isoformat(),
    }
    inspection_response = await async_client.post(
        "/api/v1/inspections", json=inspection_payload, headers=headers
    )
    assert inspection_response.status_code == 201
    inspection_id = inspection_response.json()["id"]

    payload = {
        "inspection_id": inspection_id,
        "description": "Provide corrective action plan",
        "due_at": date.today().isoformat(),
    }
    response = await async_client.post("/api/v1/prescriptions", json=payload, headers=headers)
    assert response.status_code == 201
    prescription_id = response.json()["id"]

    list_response = await async_client.get(
        "/api/v1/prescriptions?inspection_id=" + inspection_id, headers=headers
    )
    assert list_response.status_code == 200
    assert any(item["id"] == prescription_id for item in list_response.json()["items"])

    # Status now moves only through /transition, following the FSM
    # (OPEN -> IN_PROGRESS -> COMPLETED). A direct OPEN -> COMPLETED jump is no
    # longer valid, and PATCH no longer accepts `status`.
    move_in_progress = await async_client.post(
        f"/api/v1/prescriptions/{prescription_id}/transition",
        json={"to": PrescriptionStatus.IN_PROGRESS.value},
        headers=headers,
    )
    assert move_in_progress.status_code == 200, move_in_progress.text

    update_response = await async_client.post(
        f"/api/v1/prescriptions/{prescription_id}/transition",
        json={"to": PrescriptionStatus.COMPLETED.value, "evidence": "corrective plan attached"},
        headers=headers,
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["status"] == PrescriptionStatus.COMPLETED.value

    async with sessionmaker() as session:
        logs = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "prescription",
                    AuditLog.object_id == prescription_id,
                )
            )
        ).scalars().all()
        assert logs


@pytest.mark.anyio
async def test_prescription_tenant_isolation(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        other_tenant = await data_factory.ensure_tenant(slug="acme", session=session)
        other_company = await data_factory.create_company(tenant=other_tenant, session=session)
        other_site = await data_factory.create_site(tenant=other_tenant, company=other_company, session=session)
        other_inspection = Inspection(
            tenant_id=other_tenant.id,
            company_id=other_company.id,
            site_id=other_site.id,
            authority="Other authority",
        )
        session.add(other_inspection)
        await session.flush()
        other_inspection_id = other_inspection.id
        session.add(
            Prescription(
                tenant_id=other_tenant.id,
                inspection_id=other_inspection.id,
                description="Other tenant prescription",
            )
        )
        await session.commit()

    inspection_payload = {
        "company_id": company.id,
        "site_id": site.id,
        "authority": "Ростехнадзор",
        "scheduled_at": date.today().isoformat(),
    }
    inspection_response = await async_client.post(
        "/api/v1/inspections", json=inspection_payload, headers=headers
    )
    assert inspection_response.status_code == 201
    inspection_id = inspection_response.json()["id"]

    response = await async_client.post(
        "/api/v1/prescriptions",
        json={
            "inspection_id": inspection_id,
            "description": "Plan due",
            "due_at": date.today().isoformat(),
        },
        headers=headers,
    )
    assert response.status_code == 201

    list_response = await async_client.get("/api/v1/prescriptions", headers=headers)
    assert list_response.status_code == 200
    assert all(
        item["inspection_id"] != other_inspection_id for item in list_response.json()["items"]
    )
