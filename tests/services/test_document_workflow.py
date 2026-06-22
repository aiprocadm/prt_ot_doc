from __future__ import annotations

import pytest

from app.models.document import DocumentStatus
from app.services.documents import (
    DocumentWorkflowService,
    InvalidStatusTransitionError,
)
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_document_status_changes(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        document, _ = await data_factory.create_document(
            tenant=tenant, status=DocumentStatus.DRAFT, session=session
        )
        service = DocumentWorkflowService(session)

        updated = await service.change_status(
            document_id=document.id,
            tenant_id=str(tenant.id),
            new_status=DocumentStatus.GENERATED,
            actor_id=None,
            ip="127.0.0.1",
        )

        assert updated.status is DocumentStatus.GENERATED


@pytest.mark.asyncio
async def test_invalid_status_transition_raises(sessionmaker, data_factory: TestDataFactory):
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        document, _ = await data_factory.create_document(
            tenant=tenant, status=DocumentStatus.SIGNED, session=session
        )
        service = DocumentWorkflowService(session)

        with pytest.raises(InvalidStatusTransitionError):
            await service.change_status(
                document_id=document.id,
                tenant_id=str(tenant.id),
                new_status=DocumentStatus.REVIEW,
                actor_id=None,
                ip="127.0.0.1",
            )
