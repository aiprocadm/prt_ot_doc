from __future__ import annotations

import pytest
from fastapi import status
from sqlalchemy import select

from app.models.document import DocumentStatus
from app.models.models import Outbox, RoleEnum
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_document_signed_emits_outbox(
    async_client, make_auth_headers, sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        document, version = await data_factory.create_document(
            tenant=tenant,
            session=session,
            status=DocumentStatus.APPROVED,
        )
        tenant_id = str(tenant.id)

    headers = await make_auth_headers(RoleEnum.ADMIN)
    response = await async_client.patch(
        f"/api/v1/documents/{document.id}/status",
        json={"to": "signed"},
        headers=headers,
    )
    assert response.status_code == status.HTTP_200_OK

    async with sessionmaker() as session:
        outbox_entry = (
            await session.execute(
                select(Outbox).where(
                    Outbox.tenant_id == tenant_id,
                    Outbox.event_type == "DocumentSigned",
                )
            )
        ).scalar_one_or_none()
        assert outbox_entry is not None
        assert outbox_entry.payload["document_version_id"] == version.id
