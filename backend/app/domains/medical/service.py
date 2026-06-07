"""Medical domain I/O service (TZ B.8)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.medical import lifecycle as lc
from app.models.models import (
    MedicalExam, MedicalExamKind, MedicalFitness, MedicalNorm,
    MedicalSuspension, MedicalSuspensionStatus, Person,
)
from app.services.events import EventType
from app.services.outbox import OutboxService


async def list_active_suspensions(
    session: AsyncSession, *, tenant_id: str, person_ids: list[str]
) -> list[MedicalSuspension]:
    if not person_ids:
        return []
    stmt = select(MedicalSuspension).where(
        MedicalSuspension.tenant_id == tenant_id,
        MedicalSuspension.deleted_at.is_(None),
        MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE,
        MedicalSuspension.person_id.in_(person_ids),
    )
    return list((await session.execute(stmt)).scalars().all())


async def _norm_interval(
    session: AsyncSession, *, tenant_id: str, person: Person, exam_kind: MedicalExamKind
) -> int:
    if person.position_id is None:
        return lc.interval_for_kind(exam_kind, None)
    stmt = select(MedicalNorm.interval_days).where(
        MedicalNorm.tenant_id == tenant_id,
        MedicalNorm.position_id == person.position_id,
        MedicalNorm.exam_kind == exam_kind,
    ).limit(1)
    interval = (await session.execute(stmt)).scalar_one_or_none()
    return lc.interval_for_kind(exam_kind, interval)


async def record_exam(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, person_id: str,
    exam_kind: MedicalExamKind, exam_date: date, fitness: MedicalFitness | None,
    contraindications: list[str], conclusion: str | None, restrictions: str | None,
    valid_until: date | None, medical_org_name: str | None, referral_id: str | None,
    exam_type: str | None,
) -> MedicalExam:
    person = (await session.execute(
        select(Person).where(
            Person.id == person_id, Person.tenant_id == tenant_id, Person.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if person is None:
        raise ValueError({"code": "person_not_found", "person_id": person_id})

    if valid_until is None:
        interval = await _norm_interval(session, tenant_id=tenant_id, person=person, exam_kind=exam_kind)
        valid_until = lc.compute_valid_until(exam_date, interval)

    exam = MedicalExam(
        tenant_id=tenant_id, person_id=person_id, exam_kind=exam_kind,
        exam_type=exam_type or exam_kind.value, exam_date=exam_date, fitness=fitness,
        conclusion=conclusion, restrictions=restrictions,
        contraindications=list(contraindications or []), valid_until=valid_until,
        medical_org_name=medical_org_name, referral_id=referral_id,
    )
    session.add(exam)
    await session.flush()

    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=tenant_id, event_type=EventType.MEDICAL_EXAM_RECORDED.value,
        idempotency_key=f"medical-exam:{exam.id}",
        payload={
            "tenant_id": tenant_id, "actor_id": actor_id, "exam_id": exam.id,
            "person_id": person_id, "exam_kind": exam_kind.value,
            "fitness": fitness.value if fitness else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
        },
    )

    if fitness is not None:
        await _apply_suspension(session, tenant_id=tenant_id, actor_id=actor_id,
                                person_id=person_id, exam=exam, fitness=fitness)
    return exam


async def _apply_suspension(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, person_id: str,
    exam: MedicalExam, fitness: MedicalFitness,
) -> None:
    actives = await list_active_suspensions(session, tenant_id=tenant_id, person_ids=[person_id])
    action = lc.suspension_action(bool(actives), fitness)
    outbox = OutboxService(session)
    if action is lc.SuspensionAction.OPEN:
        susp = MedicalSuspension(
            tenant_id=tenant_id, person_id=person_id,
            reason=lc.reason_for(exam.contraindications), source_exam_id=exam.id,
            started_at=datetime.now(tz=timezone.utc), status=MedicalSuspensionStatus.ACTIVE,
        )
        session.add(susp)
        await session.flush()
        await outbox.enqueue(
            tenant_id=tenant_id, event_type=EventType.PERSON_SUSPENDED.value,
            idempotency_key=f"person-suspended:{susp.id}",
            payload={
                "tenant_id": tenant_id, "actor_id": actor_id,
                "suspension_id": susp.id, "person_id": person_id,
                "reason": susp.reason.value, "source_exam_id": exam.id,
            },
        )
    elif action is lc.SuspensionAction.LIFT:
        for susp in actives:
            susp.status = MedicalSuspensionStatus.LIFTED
            susp.lifted_at = datetime.now(tz=timezone.utc)
            susp.lifted_by = actor_id
            await outbox.enqueue(
                tenant_id=tenant_id, event_type=EventType.PERSON_REINSTATED.value,
                idempotency_key=f"person-reinstated:{susp.id}",
                payload={
                    "tenant_id": tenant_id, "actor_id": actor_id,
                    "suspension_id": susp.id, "person_id": person_id,
                },
            )
