from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.models.document import DocumentStatus
from app.models.obligations import Task, TaskStatus
from app.services.documents import DocumentWorkflowService
from app.services.domain_hooks import on_document_signed_create_followup_task
from tests.utils.factories import TestDataFactory


@pytest.mark.asyncio
async def test_signed_document_creates_followup_task(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        document, _ = await data_factory.create_document(
            tenant=tenant, status=DocumentStatus.APPROVED, session=session
        )
        service = DocumentWorkflowService(session)
        await service.change_status(
            document_id=document.id,
            tenant_id=str(tenant.id),
            new_status=DocumentStatus.SIGNED,
            actor_id=None,
            ip="127.0.0.1",
        )
        await session.commit()

    async with sessionmaker() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.tenant_id == str(tenant.id),
                    Task.entity_type == "document",
                    Task.entity_id == document.id,
                    Task.status == TaskStatus.OPEN,
                )
            )
        ).scalar_one()
        assert int(count or 0) == 1


@pytest.mark.asyncio
async def test_followup_task_is_idempotent(
    sessionmaker, data_factory: TestDataFactory
) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        document, _ = await data_factory.create_document(
            tenant=tenant, status=DocumentStatus.SIGNED, session=session
        )
        await on_document_signed_create_followup_task(session, document=document, actor_id=None)
        await on_document_signed_create_followup_task(session, document=document, actor_id=None)
        await session.commit()

    async with sessionmaker() as session:
        count = (
            await session.execute(
                select(func.count())
                .select_from(Task)
                .where(
                    Task.tenant_id == str(tenant.id),
                    Task.entity_id == document.id,
                )
            )
        ).scalar_one()
        assert int(count or 0) == 1
