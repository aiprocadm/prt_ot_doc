from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.models import Outbox, RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_ppe_issue_emits_outbox(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        company = await data_factory.create_company(tenant=tenant, session=session)
        person = await data_factory.create_person(tenant=tenant, company=company, session=session)
        tenant_id = str(tenant.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)

    item_payload = {"name": "Helmet", "code": "PPE-HELM", "category": "head"}
    item_response = await async_client.post(
        "/api/v1/ppe/items", json=item_payload, headers=headers
    )
    assert item_response.status_code == status.HTTP_201_CREATED
    item_id = item_response.json()["id"]

    issue_payload = {"person_id": person.id, "item_id": item_id, "quantity": 1}
    issue_response = await async_client.post(
        "/api/v1/ppe/issues", json=issue_payload, headers=headers
    )
    assert issue_response.status_code == status.HTTP_201_CREATED
    issue_id = issue_response.json()["id"]

    async with sessionmaker() as session:
        outbox_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == tenant_id,
                    Outbox.event_type == "PPEIssued",
                )
            )
        ).scalar_one_or_none()
        assert outbox_entry is not None
        assert outbox_entry.payload["issue_id"] == issue_id
