from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import select

from app.models.models import (
    BriefingEntry,
    BriefingJournal,
    ExternalRegistryJob,
    OfflineSyncBatch,
    Tenant,
    TrainingCertificate,
    TrainingEnrollment,
    TrainingProgram,
    TrainingTest,
)
from app.modules.briefings.services import BriefingEntryService
from app.modules.external_registry.services import ExternalRegistryDispatchService
from app.modules.pwa_sync.services import OfflineSyncService
from app.modules.training.services import TrainingEnrollmentService


async def _tenant_id(session) -> str:
    return (await session.execute(select(Tenant.id).where(Tenant.slug == "test"))).scalar_one()


@pytest.mark.anyio
async def test_enrollment_attempt_sets_pass_and_expiry(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        program = TrainingProgram(
            tenant_id=tenant_id,
            code="OT-001",
            title="OT Program",
            category="ot",
            kind="program",
            status="active",
            validity_months=12,
        )
        session.add(program)
        await session.flush()
        test = TrainingTest(
            tenant_id=tenant_id,
            training_program_id=program.id,
            title="Main test",
            status="active",
            passing_score=80,
            attempts_limit=2,
        )
        enrollment = TrainingEnrollment(
            tenant_id=tenant_id,
            training_program_id=program.id,
            assignment_source="manual",
            assigned_at=datetime.now(tz=timezone.utc),
            status="assigned",
        )
        session.add_all([test, enrollment])
        await session.flush()

        service = TrainingEnrollmentService()
        await service.start(session, enrollment)
        attempt = await service.submit_attempt(session, enrollment, {"score": 90})

        assert attempt.passed is True
        assert enrollment.status == "passed"
        assert enrollment.completed_at is not None
        assert enrollment.expires_at is not None
        assert enrollment.expires_at.year == enrollment.completed_at.year + 1


@pytest.mark.anyio
async def test_briefing_complete_requires_both_signatures(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        journal = BriefingJournal(
            tenant_id=tenant_id,
            code="BJ-001",
            title="Main journal",
            journal_type="workplace",
            status="active",
        )
        session.add(journal)
        await session.flush()
        entry = BriefingEntry(
            tenant_id=tenant_id,
            briefing_journal_id=journal.id,
            briefing_template_id=None,
            briefing_type="primary",
            briefing_date=datetime.now(tz=timezone.utc),
            status="draft",
        )
        session.add(entry)
        await session.flush()

        service = BriefingEntryService()
        await service.sign(session, entry, "employee", "user-1")
        with pytest.raises(ValueError):
            await service.complete(session, entry)

        await service.sign(session, entry, "instructor", "user-2")
        await service.complete(session, entry)
        assert entry.status == "completed"


@pytest.mark.anyio
async def test_offline_sync_rejects_completed_conflict(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        journal = BriefingJournal(
            tenant_id=tenant_id,
            code="BJ-002",
            title="Secondary journal",
            journal_type="workplace",
            status="active",
        )
        session.add(journal)
        await session.flush()
        entry = BriefingEntry(
            tenant_id=tenant_id,
            briefing_journal_id=journal.id,
            briefing_template_id=None,
            briefing_type="repeat",
            briefing_date=datetime.now(tz=timezone.utc),
            status="completed",
        )
        session.add(entry)
        await session.flush()

        batch = OfflineSyncBatch(
            tenant_id=tenant_id,
            user_id="user-1",
            device_id="dev-1",
            entity_type="briefing_entry",
            payload={"entity_type": "briefing_entry", "id": entry.id},
            status="pending",
        )
        session.add(batch)
        await session.flush()

        result = await OfflineSyncService().apply_batch(session, batch)
        assert result.status == "failed"
        assert result.error_payload == {"error": "conflict_final_record"}


@pytest.mark.anyio
async def test_registry_dispatch_updates_certificate_status(sessionmaker) -> None:
    async with sessionmaker() as session:
        tenant_id = await _tenant_id(session)
        program = TrainingProgram(
            tenant_id=tenant_id,
            code="OT-002",
            title="OT Program 2",
            category="ot",
            kind="program",
            status="active",
        )
        session.add(program)
        await session.flush()

        certificate = TrainingCertificate(
            tenant_id=tenant_id,
            code="CERT-1",
            training_program_id=program.id,
            issued_at=date.today(),
            status="active",
            external_registry_status="pending",
        )
        session.add(certificate)
        await session.flush()

        service = ExternalRegistryDispatchService()
        job = await service.enqueue(session, tenant_id, "certificate", certificate.id, "frdo")
        dispatched = await service.dispatch(session, job)

        assert dispatched.status in {"accepted", "rejected"}
        assert certificate.external_registry_status == dispatched.status
        assert certificate.external_registry_payload is not None

        jobs = (
            await session.execute(
                select(ExternalRegistryJob).where(ExternalRegistryJob.tenant_id == tenant_id)
            )
        ).scalars().all()
        assert len(jobs) == 1
