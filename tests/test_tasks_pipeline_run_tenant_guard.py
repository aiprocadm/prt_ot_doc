"""Tenant guard on document pipeline run resolution (background path).

SQLite tests use a single physical schema: ``session.get(PipelineRun, pk)`` can return
another tenant's row. HTTP APIs rely on scoped queries; Celery must validate ``run.tenant_id``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

import app.tasks as task_module
from app.models.document import (
    DocumentBatchItem,
    DocumentBatchItemStatus,
    DocumentBatchRun,
    DocumentBatchStatus,
)
from app.models.models import (
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.tasks import _assert_batch_item_scope, _generate_document_for_run


@pytest.fixture()
def override_task_session_scope(monkeypatch, sessionmaker):
    @asynccontextmanager
    async def _scope(*, tenant: str | None = None):
        slug = (tenant or "test").strip().lower()
        async with sessionmaker() as session:
            session.info["tenant"] = slug
            row = (
                await session.execute(select(Tenant.id).where(Tenant.slug == slug).limit(1))
            ).scalar_one_or_none()
            if row is not None:
                session.info["tenant_id"] = str(row)
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    monkeypatch.setattr(task_module, "session_scope", _scope)
    monkeypatch.setattr(task_module, "ensure_tenant_schema", lambda _slug: None)


@pytest.mark.asyncio()
@pytest.mark.usefixtures("override_task_session_scope")
async def test_generate_document_run_rejects_wrong_tenant_slug(
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        acme = await data_factory.ensure_tenant(slug="acme", session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)

        template = Template(
            tenant_id=acme.id,
            name="guard-template",
            metadata_json={},
            storage_key="acme/templates/guard.docx",
        )
        session.add(template)
        await session.flush()
        version = TemplateVersion(
            tenant_id=acme.id,
            template_id=template.id,
            version=1,
            checksum=b"chk",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="acme/templates/guard.docx",
        )
        session.add(version)
        await session.flush()
        run = PipelineRun(
            tenant_id=acme.id,
            template_id=template.id,
            template_version_id=version.id,
            status=PipelineRunStatus.QUEUED,
            context={},
            idempotency_key="tenant-guard-run-1",
            result_metadata={"company_id": "c1", "initiated_by": "u1"},
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    with pytest.raises(ValueError, match="Pipeline run not found"):
        await _generate_document_for_run(run_id, "beta")


@pytest.mark.asyncio()
@pytest.mark.usefixtures("override_task_session_scope")
async def test_generate_document_run_accepts_matching_tenant_slug(
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        acme = await data_factory.ensure_tenant(slug="acme", session=session)
        template = Template(
            tenant_id=acme.id,
            name="guard-template-2",
            metadata_json={},
            storage_key="acme/templates/guard2.docx",
        )
        session.add(template)
        await session.flush()
        version = TemplateVersion(
            tenant_id=acme.id,
            template_id=template.id,
            version=1,
            checksum=b"chk2",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="acme/templates/guard2.docx",
        )
        session.add(version)
        await session.flush()
        run = PipelineRun(
            tenant_id=acme.id,
            template_id=template.id,
            template_version_id=version.id,
            status=PipelineRunStatus.QUEUED,
            context={},
            idempotency_key="tenant-guard-run-2",
            result_metadata={"company_id": "c1", "initiated_by": "u1"},
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        run_id = run.id

    with pytest.raises(ValueError, match="Company not found"):
        await _generate_document_for_run(run_id, "acme")


@pytest.mark.asyncio()
@pytest.mark.usefixtures("override_task_session_scope")
async def test_batch_item_scope_rejects_cross_tenant(
    sessionmaker,
    data_factory,
) -> None:
    async with sessionmaker() as session:
        acme = await data_factory.ensure_tenant(slug="acme", session=session)
        await data_factory.ensure_tenant(slug="beta", session=session)
        user = await data_factory.create_user(tenant=acme, session=session)
        company = await data_factory.create_company(tenant=acme, session=session)
        template = Template(
            tenant_id=acme.id,
            name="batch-guard-tpl",
            metadata_json={},
            storage_key="acme/templates/batch.docx",
        )
        session.add(template)
        await session.flush()
        version = TemplateVersion(
            tenant_id=acme.id,
            template_id=template.id,
            version=1,
            checksum=b"bchk",
            status=TemplateVersionStatus.ACTIVE,
            payload_key="acme/templates/batch.docx",
        )
        session.add(version)
        await session.flush()
        batch = DocumentBatchRun(
            tenant_id=acme.id,
            template_id=template.id,
            template_version_id=version.id,
            company_id=company.id,
            created_by=user.id,
            status=DocumentBatchStatus.PENDING,
            total=1,
            processed=0,
            succeeded=0,
            failed=0,
        )
        session.add(batch)
        await session.flush()
        item = DocumentBatchItem(
            tenant_id=acme.id,
            batch_id=batch.id,
            row_index=0,
            payload={},
            status=DocumentBatchItemStatus.PENDING,
        )
        session.add(item)
        await session.commit()
        batch_id, item_id = batch.id, item.id

    async with sessionmaker() as beta_session:
        beta_session.info["tenant"] = "beta"
        beta_tid = (
            await beta_session.execute(select(Tenant.id).where(Tenant.slug == "beta").limit(1))
        ).scalar_one_or_none()
        assert beta_tid is not None
        beta_session.info["tenant_id"] = str(beta_tid)
        b_row = await beta_session.get(DocumentBatchRun, batch_id)
        i_row = await beta_session.get(DocumentBatchItem, item_id)
        with pytest.raises(ValueError, match="Batch item not found"):
            _assert_batch_item_scope(beta_session, b_row, i_row, batch_id=batch_id, item_id=item_id)
