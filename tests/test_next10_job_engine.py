from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.job_engine import DocumentArtifact, DocumentJob, OutboxEvent
from app.db import session_scope
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
            enqueue=False,
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
            enqueue=False,
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
            enqueue=False,
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
            enqueue=False,
        )
        await orchestrator.run_job(job_id=job.id)
        events = (await session.execute(select(OutboxEvent).where(OutboxEvent.tenant_id == "tenant-1"))).scalars().all()
        assert any(e.event_type == "DocumentGenerated" for e in events)




@pytest.mark.anyio
async def test_idempotency_parallel_wait_returns_same_response(sessionmaker) -> None:
    async with sessionmaker() as first_session:
        idem1 = IdempotencyService(session=first_session, tenant_id="tenant-1", endpoint="documents.generate")
        record, _ = await idem1.acquire(key="race-key", request_hash="hash-race")
        await first_session.flush()

        async def second_request() -> str:
            async with sessionmaker() as second_session:
                idem2 = IdempotencyService(session=second_session, tenant_id="tenant-1", endpoint="documents.generate")
                rec2, created2 = await idem2.acquire(key="race-key", request_hash="hash-race", wait_timeout_seconds=1.0)
                assert created2 is False
                return str(rec2.status)

        task = asyncio.create_task(second_request())
        await asyncio.sleep(0.05)
        await idem1.store_success(record, status_code=202, body={"job_id": "job-race"})
        await first_session.commit()
        status_value = await task
        assert status_value == "IdempotencyStatus.SUCCEEDED"


@pytest.mark.anyio
async def test_dispatch_outbox_events_retries_and_poisoned(sessionmaker) -> None:
    from datetime import datetime, timezone

    from app.models.job_engine import OutboxEventStatus
    from app.tasks import _dispatch_outbox_events

    async with session_scope(tenant="tenant-1") as session:
        session.add(
            OutboxEvent(
                tenant_id="tenant-1",
                event_type="DocumentGenerated",
                event_id="evt-fail",
                payload={"force_fail": True},
                status=OutboxEventStatus.PENDING.value,
                next_attempt_at=datetime.now(tz=timezone.utc),
            )
        )
        await session.commit()

    await _dispatch_outbox_events(max_attempts=1, tenant_slug="tenant-1")

    async with session_scope(tenant="tenant-1") as session:
        event = (await session.execute(select(OutboxEvent).where(OutboxEvent.event_id == "evt-fail"))).scalar_one()
        assert event.status == OutboxEventStatus.POISONED.value
        assert event.attempts >= 1


@pytest.mark.anyio
async def test_dispatch_outbox_events_sends_pending(sessionmaker) -> None:
    from datetime import datetime, timezone

    from app.models.job_engine import OutboxEventStatus
    from app.tasks import _dispatch_outbox_events

    async with session_scope(tenant="tenant-1") as session:
        session.add(
            OutboxEvent(
                tenant_id="tenant-1",
                event_type="DocumentGenerated",
                event_id="evt-ok",
                payload={"hello": "world"},
                status=OutboxEventStatus.PENDING.value,
                next_attempt_at=datetime.now(tz=timezone.utc),
            )
        )
        await session.commit()

    processed = await _dispatch_outbox_events(max_attempts=2, tenant_slug="tenant-1")
    assert processed >= 1

    async with session_scope(tenant="tenant-1") as session:
        event = (await session.execute(select(OutboxEvent).where(OutboxEvent.event_id == "evt-ok"))).scalar_one()
        assert event.status == OutboxEventStatus.SENT.value
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
            enqueue=False,
        )
        await orchestrator.cancel_job(job_id=job.id)
        refreshed = await session.get(DocumentJob, job.id)
        assert refreshed is not None
        assert refreshed.status == "canceled"
