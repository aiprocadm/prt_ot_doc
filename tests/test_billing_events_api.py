from __future__ import annotations

from app.models.models import BillingEvent, BillingEventType, Tenant
from sqlalchemy import select


async def test_billing_events_list(async_client, sessionmaker, make_auth_headers) -> None:
    headers = await make_auth_headers()

    async with sessionmaker() as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == "test"))).scalar_one()
        session.add(
            BillingEvent(
                tenant_id=tenant.id,
                type=BillingEventType.PLAN_CHANGED,
                ref_type="subscription",
                ref_id="sub-1",
                payload={"plan_code": "professional"},
            )
        )
        await session.commit()

    response = await async_client.get("/api/v1/billing/events", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body
    assert body[0]["event_type"] == "plan_changed"
    assert body[0]["payload"]["plan_code"] == "professional"
