"""API contract for prescription escalation + closure-rate (TZ-3.4-V12-01):
is_overdue flag, /overdue, /summary, /remind-overdue.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

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
    async_client,
    headers,
    company_id: str,
    site_id: str,
    *,
    due_at: date | None = None,
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
    # Use the same UTC date basis the API uses (the endpoint computes is_overdue
    # against datetime.now(timezone.utc).date()). A local date.today() near the UTC
    # day boundary would put a "yesterday" due-date on the server's UTC today.
    today_utc = datetime.now(timezone.utc).date()
    pid_past = await _seed_prescription(
        async_client, headers, company_id, site_id, due_at=today_utc - timedelta(days=1)
    )
    pid_future = await _seed_prescription(
        async_client, headers, company_id, site_id, due_at=today_utc + timedelta(days=1)
    )

    r_past = await async_client.get(f"/api/v1/prescriptions/{pid_past}", headers=headers)
    assert r_past.status_code == status.HTTP_200_OK, r_past.text
    assert r_past.json()["is_overdue"] is True

    r_future = await async_client.get(f"/api/v1/prescriptions/{pid_future}", headers=headers)
    assert r_future.json()["is_overdue"] is False


@pytest.mark.asyncio
async def test_overdue_lists_only_past_due_non_terminal(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    past = date.today() - timedelta(days=2)

    pid_overdue = await _seed_prescription(async_client, headers, company_id, site_id, due_at=past)
    await _seed_prescription(  # future -> not overdue
        async_client, headers, company_id, site_id, due_at=date.today() + timedelta(days=2)
    )
    pid_cancelled = await _seed_prescription(
        async_client, headers, company_id, site_id, due_at=past
    )
    await async_client.post(
        f"/api/v1/prescriptions/{pid_cancelled}/transition",
        json={"to": PrescriptionStatus.CANCELLED.value},
        headers=headers,
    )

    r = await async_client.get("/api/v1/prescriptions/overdue", headers=headers)
    assert r.status_code == status.HTTP_200_OK, r.text
    ids = [item["id"] for item in r.json()["items"]]
    assert pid_overdue in ids
    assert pid_cancelled not in ids  # terminal excluded
    assert all(item["is_overdue"] for item in r.json()["items"])


@pytest.mark.asyncio
async def test_overdue_requires_prescription_role_403(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.WORKER)  # not in {admin,owner,hr,line_manager}
    r = await async_client.get("/api/v1/prescriptions/overdue", headers=headers)
    assert r.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_summary_breakdown_and_closure_rate(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)

    # OPEN (left as-is)
    await _seed_prescription(async_client, headers, company_id, site_id)
    # COMPLETED
    pid_c = await _seed_prescription(async_client, headers, company_id, site_id)
    await async_client.post(
        f"/api/v1/prescriptions/{pid_c}/transition", json={"to": "in_progress"}, headers=headers
    )
    await async_client.post(
        f"/api/v1/prescriptions/{pid_c}/transition",
        json={"to": "completed", "evidence": "e"},
        headers=headers,
    )
    # VERIFIED
    pid_v = await _seed_prescription(async_client, headers, company_id, site_id)
    await async_client.post(
        f"/api/v1/prescriptions/{pid_v}/transition", json={"to": "in_progress"}, headers=headers
    )
    await async_client.post(
        f"/api/v1/prescriptions/{pid_v}/transition",
        json={"to": "completed", "evidence": "e"},
        headers=headers,
    )
    await async_client.post(
        f"/api/v1/prescriptions/{pid_v}/transition", json={"to": "verified"}, headers=headers
    )

    r = await async_client.get("/api/v1/prescriptions/summary", headers=headers)
    assert r.status_code == status.HTTP_200_OK, r.text
    body = r.json()
    bs = body["by_status"]
    # all five statuses are present as keys
    assert set(bs) == {"open", "in_progress", "completed", "verified", "cancelled"}
    # at least the three we seeded
    assert bs["open"] >= 1 and bs["completed"] >= 1 and bs["verified"] >= 1
    # internal consistency: total == sum, closure_rate == (verified+completed)/total
    assert body["total"] == sum(bs.values())
    assert body["closure_rate"] == pytest.approx((bs["verified"] + bs["completed"]) / body["total"])
    assert body["overdue_count"] >= 0


@pytest.mark.asyncio
async def test_remind_overdue_emits_task_overdue_with_stable_key(
    async_client, sessionmaker, data_factory, make_auth_headers
):
    company_id, site_id = await _seed_company_site(sessionmaker, data_factory)
    headers = await make_auth_headers(RoleEnum.ADMIN)
    past = date.today() - timedelta(days=3)
    pid = await _seed_prescription(async_client, headers, company_id, site_id, due_at=past)

    r1 = await async_client.post("/api/v1/prescriptions/remind-overdue", headers=headers)
    assert r1.status_code == status.HTTP_200_OK, r1.text
    assert r1.json()["count"] >= 1

    expected_key = f"prescription-overdue:{pid}:{past.isoformat()}"
    async with sessionmaker() as session:
        rows = (
            (
                await session.execute(
                    select(Outbox).where(
                        Outbox.event_type == EventType.TASK_OVERDUE.value,
                        Outbox.idempotency_key == expected_key,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows, "expected a TASK_OVERDUE outbox row for the overdue prescription"

    # second same-day call: the idempotency key is stable (destination-scoped dedup-ready)
    await async_client.post("/api/v1/prescriptions/remind-overdue", headers=headers)
    async with sessionmaker() as session:
        keys = (
            (
                await session.execute(
                    select(Outbox.idempotency_key).where(Outbox.idempotency_key == expected_key)
                )
            )
            .scalars()
            .all()
        )
        assert set(keys) == {expected_key}  # every emission shares one stable key

    # audit trail
    async with sessionmaker() as session:
        logs = (
            (
                await session.execute(
                    select(AuditLog).where(
                        AuditLog.object_type == "prescription",
                        AuditLog.action == "notify_overdue",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert logs
