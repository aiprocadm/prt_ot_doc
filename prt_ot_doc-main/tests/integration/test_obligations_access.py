from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from app.models.models import AuditLog, RoleEnum


@pytest.mark.anyio
async def test_worker_can_only_view_assigned_tasks(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        worker = await data_factory.create_user(
            tenant=tenant, role=RoleEnum.WORKER, email="worker@example.com", session=session
        )
        other_user = await data_factory.create_user(
            tenant=tenant, role=RoleEnum.ADMIN, email="admin+other@example.com", session=session
        )
        await session.commit()

    admin_headers = await make_auth_headers(RoleEnum.ADMIN)
    worker_headers = await make_auth_headers(RoleEnum.WORKER, email="worker@example.com")

    payload = {
        "company_id": company.id,
        "site_id": site.id,
        "authority": "Ростехнадзор",
        "scheduled_at": date.today().isoformat(),
        "responsible_id": worker.id,
    }
    response = await async_client.post("/api/v1/inspections", json=payload, headers=admin_headers)
    assert response.status_code == 201

    other_payload = {
        "company_id": company.id,
        "site_id": site.id,
        "authority": "Пожнадзор",
        "scheduled_at": date.today().isoformat(),
        "responsible_id": other_user.id,
    }
    response = await async_client.post(
        "/api/v1/inspections", json=other_payload, headers=admin_headers
    )
    assert response.status_code == 201

    tasks_response = await async_client.get("/api/v1/tasks", headers=worker_headers)
    assert tasks_response.status_code == 200
    tasks = tasks_response.json()["items"]
    assert tasks
    assert all(task["assignee_id"] == worker.id for task in tasks)


@pytest.mark.anyio
async def test_worker_cannot_create_inspection(async_client, make_auth_headers):
    worker_headers = await make_auth_headers(RoleEnum.WORKER)
    response = await async_client.post(
        "/api/v1/inspections",
        json={"company_id": "x", "authority": "Test"},
        headers=worker_headers,
    )
    assert response.status_code == 403


@pytest.mark.anyio
async def test_attestation_audit_log(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    headers = await make_auth_headers(RoleEnum.ADMIN)
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        await session.commit()

    payload = {"person_id": person.id, "name": "First Aid", "expires_at": date.today().isoformat()}
    response = await async_client.post("/api/v1/attestations", json=payload, headers=headers)
    assert response.status_code == 201
    attestation_id = response.json()["id"]

    async with sessionmaker() as session:
        logs = (
            await session.execute(
                select(AuditLog).where(
                    AuditLog.object_type == "attestation",
                    AuditLog.object_id == attestation_id,
                )
            )
        ).scalars().all()
        assert logs
