from __future__ import annotations

import pytest
from sqlalchemy import Column, String, Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import TenantBase
from app.models.job_engine import DocumentJobStep, JobStepStatus
from app.modules.pipelines.models import PipelineProfile
from app.services.file_storage import FileStorageService
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator, PipelineOrchestrator


@pytest.fixture()
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    if "tenant" not in TenantBase.metadata.tables:
        Table("tenant", TenantBase.metadata, Column("id", String(36), primary_key=True))
    async with engine.begin() as conn:
        await conn.run_sync(TenantBase.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.fixture(autouse=True)
def _disable_audit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(PipelineOrchestrator, "_audit_action", _noop)
    monkeypatch.setattr(PipelineOrchestrator, "_audit_diff", _noop)
    monkeypatch.setattr(PipelineOrchestrator, "_audit_step", _noop)
    FileStorageService.default().clear()


async def _seed_profile(session, *, tenant_id: str, code: str = "pkg-doc") -> PipelineProfile:
    profile = PipelineProfile(
        tenant_id=tenant_id,
        code=code,
        name="Документы",
        is_active=True,
        steps=[
            {"code": "render_docx"},
            {"code": "apply_headers"},
            {"code": "replace_apply"},
            {"code": "convert_pdf"},
            {"code": "build_zip"},
            {"code": "archive"},
        ],
        graph={
            "nodes": [
                {"id": "render", "type": "render_docx", "config": {"template_code": code}},
                {"id": "headers", "type": "apply_headers"},
                {"id": "replace", "type": "replace_apply"},
                {"id": "pdf", "type": "convert_pdf"},
                {"id": "zip", "type": "build_zip"},
                {"id": "archive", "type": "archive"},
            ],
            "edges": [
                {"from": "render", "to": "headers"},
                {"from": "headers", "to": "replace"},
                {"from": "replace", "to": "pdf"},
                {"from": "pdf", "to": "zip"},
                {"from": "zip", "to": "archive"},
            ],
        },
        limits={},
    )
    session.add(profile)
    await session.flush()
    return profile


@pytest.mark.asyncio
async def test_create_job_idempotency_returns_same_job(db_session) -> None:
    await _seed_profile(db_session, tenant_id="t-1")
    orchestrator = DocumentPipelineOrchestrator(db_session)

    payload = {"template_code": "pkg-doc", "input": {"doc": "A"}}
    job1 = await orchestrator.start_document_job(
        tenant_id="t-1",
        created_by=None,
        payload=payload,
        idempotency_key="idem-1",
        request_hash="hash-1",
        correlation_id="corr-1",
        enqueue=False,
    )
    job2 = await orchestrator.start_document_job(
        tenant_id="t-1",
        created_by=None,
        payload=payload,
        idempotency_key="idem-1",
        request_hash="hash-1",
        correlation_id="corr-2",
        enqueue=False,
    )

    assert job1.id == job2.id


@pytest.mark.asyncio
async def test_pipeline_full_run_and_retry_failed_step(db_session) -> None:
    await _seed_profile(db_session, tenant_id="t-1")
    orchestrator = DocumentPipelineOrchestrator(db_session)
    payload = {"template_code": "pkg-doc", "input": {"doc": "A"}}

    job = await orchestrator.start_document_job(
        tenant_id="t-1",
        created_by=None,
        payload=payload,
        idempotency_key="idem-2",
        request_hash="hash-2",
        enqueue=False,
    )

    failed_job = await orchestrator.run_job(job_id=job.id, fail_step="convert_pdf")
    assert failed_job.status == "failed"

    convert_step = (
        await db_session.execute(
            select(DocumentJobStep).where(DocumentJobStep.job_id == job.id, DocumentJobStep.step_key == "convert_pdf")
        )
    ).scalar_one()
    assert convert_step.status == JobStepStatus.FAILED.value

    await orchestrator.retry_job(job_id=job.id, retry_failed_only=True)
    resumed = await orchestrator.run_job(job_id=job.id)
    assert resumed.status == "success"

    steps = (await db_session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id))).scalars().all()
    assert all(step.status == JobStepStatus.SUCCESS.value for step in steps)
    assert resumed.output_payload_json is not None


@pytest.mark.asyncio
async def test_cancel_marks_queued_steps_as_canceled(db_session) -> None:
    await _seed_profile(db_session, tenant_id="t-1")
    orchestrator = DocumentPipelineOrchestrator(db_session)

    job = await orchestrator.start_document_job(
        tenant_id="t-1",
        created_by=None,
        payload={"template_code": "pkg-doc", "input": {}},
        idempotency_key="idem-3",
        request_hash="hash-3",
        enqueue=False,
    )

    canceled = await orchestrator.cancel_job(job_id=job.id)
    assert canceled.status == "canceled"

    steps = (await db_session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id))).scalars().all()
    assert {s.status for s in steps} == {JobStepStatus.CANCELED.value}


@pytest.mark.asyncio
async def test_start_document_job_moves_job_to_running(db_session) -> None:
    await _seed_profile(db_session, tenant_id="t-1")
    orchestrator = DocumentPipelineOrchestrator(db_session)

    job = await orchestrator.start_document_job(
        tenant_id="t-1",
        created_by=None,
        payload={"template_code": "pkg-doc", "input": {}},
        idempotency_key="idem-4",
        request_hash="hash-4",
        enqueue=False,
    )

    assert job.status == "running"


@pytest.mark.asyncio
async def test_tenant_quota_concurrency_limit_respected(db_session) -> None:
    profile = await _seed_profile(db_session, tenant_id="t-1")
    profile.concurrency_limit_per_tenant = 1
    await db_session.flush()
    orchestrator = DocumentPipelineOrchestrator(db_session)

    first = await orchestrator.start_document_job(
        tenant_id="t-1",
        created_by=None,
        payload={"template_code": "pkg-doc", "input": {"doc": "A"}},
        idempotency_key="idem-5",
        request_hash="hash-5",
        enqueue=False,
    )
    second = await orchestrator.start_document_job(
        tenant_id="t-1",
        created_by=None,
        payload={"template_code": "pkg-doc", "input": {"doc": "B"}},
        idempotency_key="idem-6",
        request_hash="hash-6",
        enqueue=False,
    )

    assert first.status == "running"
    assert second.status == "queued"


@pytest.mark.asyncio
async def test_run_step_is_skipped_when_job_canceled(db_session) -> None:
    await _seed_profile(db_session, tenant_id="t-1")
    orchestrator = DocumentPipelineOrchestrator(db_session)

    job = await orchestrator.create_job(
        tenant_id="t-1",
        profile_code="pkg-doc",
        payload={"template_code": "pkg-doc", "input": {}},
        idempotency_key="idem-7",
        request_hash="hash-7",
    )
    steps = (await db_session.execute(select(DocumentJobStep).where(DocumentJobStep.job_id == job.id).order_by(DocumentJobStep.order.asc()))).scalars().all()
    first_step = steps[0]

    await orchestrator.cancel_job(job_id=job.id)
    step_after = await orchestrator.run_step(job_id=job.id, step_id=first_step.id)

    assert step_after.status == JobStepStatus.CANCELED.value
