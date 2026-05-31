"""API contract for prescription escalation + closure-rate (TZ-3.4-V12-01):
is_overdue flag, /overdue, /summary, /remind-overdue.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import AuditLog, Outbox, PrescriptionStatus, RoleEnum
from app.services.events import EventType


async def _seed_company_site(sessionmaker, data_factory) -> tuple[str, str]:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        site = await data_factory.create_site(tenant=tenant, company=company, session=session)
        await session.commit()
        return company.id, site.id


async def _seed_prescription(
    async_client, headers, company_id: str, site_id: str, *, due_at: date | None = None,
    description: str = "Fix guardrail",
) -> str:
    insp = await async_client.post(
        "/api/v1/inspections",
        json={
            "company_id": company_id,
            "site_id": site_id,
            "authority": "Ростехнадзор",
            "scheduled_at": date.today().isoformat(),
        },
        headers=headers,
    )
    assert insp.status_code == status.HTTP_201_CREATED, insp.text
    body = {"inspection_id": insp.json()["id"], "description": description}
    if due_at is not None:
        body["due_at"] = due_at.isoformat()
    r = await async_client.post("/api/v1/prescriptions", json=body, headers=headers)
    assert r.status_code == status.HTTP_201_CREATED, r.text
    return r.json()["id"]


@pytest.mark.asyncio
async def test_is_overdue_flag_reflects_due_date(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    pid_past = await _seed_prescription(
        async_client, headers, company_id, site_id, due_at=date.today() - timedelta(days=1)
    )
    pid_future = await _seed_prescription(
        async_client, headers, company_id, site_id, due_at=date.today() + timedelta(days=1)
    )

    r_past = await async_client.get(f"/api/v1/prescriptions/{pid_past}", headers=headers)
    assert r_past.status_code == status.HTTP_200_OK, r_past.text
    assert r_past.json()["is_overdue"] is True

    r_future = await async_client.get(f"/api/v1/prescriptions/{pid_future}", headers=headers)
    assert r_future.json()["is_overdue"] is False
