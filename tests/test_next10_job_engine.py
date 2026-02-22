from __future__ import annotations

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.job_engine import DocumentArtifact, DocumentJob, OutboxEvent
from app.services.idempotency import IdempotencyService
from app.services.pipelines_orchestrator import DocumentPipelineOrchestrator


@pytest.mark.anyio
async def test_idempotency_same_key_same_hash_returns_same_job(sessionmaker) -> None:
    async with sessionmaker() as session:
        idem = IdempotencyService(session=session, tenant_id="tenant-1", endpoint="documents.generate")
        rec1, created1 = await idem.acquire(key="key-1", request_hash="hash-1")
        await idem.store_success(rec1, status_code=202, body={"job_id": "job-1"})
        rec2, created2 = await idem.acquire(key="key-1", request_hash="hash-1")
        assert created1 is True
        assert created2 is False
        assert rec2.response_body is not None
        assert "job-1" in rec2.response_body


@pytest.mark.anyio
async def test_idempotency_same_key_diff_hash_returns_409(sessionmaker) -> None:
    async with sessionmaker() as session:
        idem = IdempotencyService(session=session, tenant_id="tenant-1", endpoint="documents.generate")
        await idem.acquire(key="key-2", request_hash="hash-1")
        with pytest.raises(HTTPException) as exc:
            await idem.acquire(key="key-2", request_hash="hash-2")
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "IDEMPOTENCY_MISMATCH"


@pytest.mark.anyio
async def test_idempotency_in_progress_returns_409(sessionmaker) -> None:
    async with sessionmaker() as session:
        idem = IdempotencyService(session=session, tenant_id="tenant-1", endpoint="documents.generate")
        await idem.acquire(key="key-pending", request_hash="hash-1")
        with pytest.raises(HTTPException) as exc:
            await idem.acquire(key="key-pending", request_hash="hash-1")
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "IDEMPOTENCY_IN_PROGRESS"


@pytest.mark.anyio
async def test_job_steps_transition_success_path(sessionmaker) -> None:
    async with sessionmaker() as session:
        orchestrator = DocumentPipelineOrchestrator(session)
        job = await orchestrator.start_document_job(
            tenant_id="tenant-1",
            created_by=None,
            payload={"template_code": "T", "template_version": 1, "options": {"zip": True}},
            idempotency_key="idem-1",
            request_hash="hash-1",
        )
        await orchestrator.run_job(job_id=job.id)
        await session.commit()
        refreshed = await session.get(DocumentJob, job.id)
        assert refreshed is not None
        assert refreshed.status == "success"


@pytest.mark.anyio
async def test_step_failure_marks_job_failed_and_sets_error(sessionmaker) -> None:
    async with sessionmaker() as session:
        orchestrator = DocumentPipelineOrchestrator(session)
        job = await orchestrator.start_document_job(
            tenant_id="tenant-1",
            created_by=None,
            payload={"template_code": "T", "template_version": 1, "options": {}},
            idempotency_key="idem-1",
            request_hash="hash-1",
        )
        await orchestrator.run_job(job_id=job.id, fail_step="convert_pdf")
        await session.commit()
        failed = await session.get(DocumentJob, job.id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_code == "step_failed"


@pytest.mark.anyio
async def test_step_retry_does_not_duplicate_artifacts(sessionmaker) -> None:
    async with sessionmaker() as session:
        orchestrator = DocumentPipelineOrchestrator(session)
        job = await orchestrator.start_document_job(
            tenant_id="tenant-1",
            created_by=None,
            payload={"template_code": "T", "template_version": 1, "options": {"zip": True}},
            idempotency_key="idem-1",
            request_hash="hash-1",
        )
        await orchestrator.run_job(job_id=job.id, fail_step="convert_pdf")
        await orchestrator.retry_job(job_id=job.id)
        artifacts = (await session.execute(select(DocumentArtifact).where(DocumentArtifact.job_id == job.id))).scalars().all()
        keys = {(a.step_code, a.kind) for a in artifacts}
        assert len(artifacts) == len(keys)


@pytest.mark.anyio
async def test_outbox_created_on_success(sessionmaker) -> None:
    async with sessionmaker() as session:
        orchestrator = DocumentPipelineOrchestrator(session)
        job = await orchestrator.start_document_job(
            tenant_id="tenant-1",
            created_by=None,
            payload={"template_code": "T", "template_version": 1, "options": {}},
            idempotency_key="idem-1",
            request_hash="hash-1",
        )
        await orchestrator.run_job(job_id=job.id)
        events = (await session.execute(select(OutboxEvent).where(OutboxEvent.tenant_id == "tenant-1"))).scalars().all()
        assert any(e.event_type == "DocumentGenerated" for e in events)


@pytest.mark.anyio
async def test_request_hash_stable_for_sorted_keys() -> None:
    from app.core.idempotency import compute_request_hash

    left = {"b": 2, "a": {"z": 1, "x": 2}}
    right = {"a": {"x": 2, "z": 1}, "b": 2}
    assert compute_request_hash(left) == compute_request_hash(right)


@pytest.mark.anyio
async def test_cancel_sets_canceled_status(sessionmaker) -> None:
    async with sessionmaker() as session:
        orchestrator = DocumentPipelineOrchestrator(session)
        job = await orchestrator.start_document_job(
            tenant_id="tenant-1",
            created_by=None,
            payload={"template_code": "T", "template_version": 1, "options": {}},
            idempotency_key="idem-1",
            request_hash="hash-1",
        )
        await orchestrator.cancel_job(job_id=job.id)
        refreshed = await session.get(DocumentJob, job.id)
        assert refreshed is not None
        assert refreshed.status == "canceled"
