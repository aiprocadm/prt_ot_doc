"""Tenant guard on document pipeline run resolution (background path).

SQLite tests use a single physical schema: ``session.get(PipelineRun, pk)`` can return
another tenant's row. HTTP APIs rely on scoped queries; Celery must validate ``run.tenant_id``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select

import app.tasks as task_module
from app.models.models import (
    PipelineRun,
    PipelineRunStatus,
    Template,
    TemplateVersion,
    TemplateVersionStatus,
    Tenant,
)
from app.tasks import _generate_document_for_run


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
