from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models.job_engine import DocumentJobStatus, DocumentJobStep, JobStepStatus
from app.modules.pipelines.models import PipelineProfile
from app.services.pipelines_orchestrator import PipelineOrchestrator


@pytest.mark.anyio
async def test_orchestrator_create_job_is_idempotent(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            PipelineProfile(
                tenant_id=str(tenant.id),
                code="doc_v1",
                name="Doc v1",
                steps=[{"code": "render_docx"}, {"code": "convert_pdf"}],
                limits={},
                is_active=True,
            )
        )
        await session.commit()

    async with sessionmaker() as session:
        orchestrator = PipelineOrchestrator(session)
        payload = {"data": {"a": 1}}
        first = await orchestrator.create_job(
            tenant_id=str(tenant.id),
            profile_code="doc_v1",
            payload=payload,
            idempotency_key="idem-1",
            request_hash="hash-1",
        )
        second = await orchestrator.create_job(
            tenant_id=str(tenant.id),
            profile_code="doc_v1",
            payload=payload,
            idempotency_key="idem-1",
            request_hash="hash-1",
        )
        assert first.id == second.id


@pytest.mark.anyio
async def test_orchestrator_retry_and_cancel_logic(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            PipelineProfile(
                tenant_id=str(tenant.id),
                code="doc_v2",
                name="Doc v2",
                steps=[{"code": "render_docx"}, {"code": "convert_pdf"}, {"code": "archive"}],
                limits={},
                is_active=True,
            )
        )
        await session.commit()

    async with sessionmaker() as session:
        orchestrator = PipelineOrchestrator(session)
        job = await orchestrator.create_job(
            tenant_id=str(tenant.id),
            profile_code="doc_v2",
            payload={"data": {}},
            idempotency_key="idem-2",
            request_hash="hash-2",
        )
        await orchestrator.start_job(job_id=job.id)
        step = await orchestrator._next_step(job.id)
        assert step is not None
        step.status = JobStepStatus.FAILED.value
        await orchestrator.retry_job(job_id=job.id, from_step_key="convert_pdf")
        assert job.status == DocumentJobStatus.QUEUED.value
        await orchestrator.cancel_job(job_id=job.id)
        assert job.status == DocumentJobStatus.CANCELED.value


@pytest.mark.anyio
async def test_retry_failed_only_keeps_successful_steps(sessionmaker, data_factory) -> None:
    async with sessionmaker() as session:
        tenant = await data_factory.ensure_tenant(session=session)
        session.add(
            PipelineProfile(
                tenant_id=str(tenant.id),
                code="doc_v3",
                name="Doc v3",
                steps=[{"code": "render_docx"}, {"code": "convert_pdf"}, {"code": "archive"}],
                limits={},
                is_active=True,
            )
        )
        await session.commit()

    async with sessionmaker() as session:
        orchestrator = PipelineOrchestrator(session)
        job = await orchestrator.create_job(
            tenant_id=str(tenant.id),
            profile_code="doc_v3",
            payload={"data": {}},
            idempotency_key="idem-3",
            request_hash="hash-3",
        )
        steps = (await session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.order.asc()))).scalars().all()
        steps[0].status = JobStepStatus.SUCCESS.value
        steps[1].status = JobStepStatus.FAILED.value
        steps[2].status = JobStepStatus.QUEUED.value
        await orchestrator.retry_job(job_id=job.id, retry_failed_only=True)
        assert steps[0].status == JobStepStatus.SUCCESS.value
        assert steps[1].status == JobStepStatus.QUEUED.value
