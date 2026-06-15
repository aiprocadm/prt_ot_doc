"""Domain services for training plans, sessions and certificates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file import File
from app.models.models import (
    Company,
    Permit,
    PermitStatus,
    Person,
    Position,
    TrainingCertificate,
    TrainingCourse,
    TrainingPlan,
    TrainingSession,
    TrainingSessionStatus,
)
from app.services.events import EventType
from app.services.obligations import create_training_task
from app.services.outbox import OutboxService


@dataclass(slots=True)
class TrainingCertificateIssueResult:
    certificate: TrainingCertificate
    permit: Permit | None = None


async def _get_company(session: AsyncSession, tenant_id: str, company_id: str) -> Company:
    stmt = select(Company).where(
        Company.id == company_id,
        Company.tenant_id == tenant_id,
        Company.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_person(session: AsyncSession, tenant_id: str, person_id: str) -> Person:
    stmt = select(Person).where(
        Person.id == person_id,
        Person.tenant_id == tenant_id,
        Person.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_position(session: AsyncSession, tenant_id: str, position_id: str) -> Position:
    stmt = select(Position).where(
        Position.id == position_id,
        Position.tenant_id == tenant_id,
        Position.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_course(session: AsyncSession, tenant_id: str, course_id: str) -> TrainingCourse:
    stmt = select(TrainingCourse).where(
        TrainingCourse.id == course_id,
        TrainingCourse.tenant_id == tenant_id,
        TrainingCourse.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def _get_plan(session: AsyncSession, tenant_id: str, plan_id: str) -> TrainingPlan:
    stmt = select(TrainingPlan).where(
        TrainingPlan.id == plan_id,
        TrainingPlan.tenant_id == tenant_id,
        TrainingPlan.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one()


async def assign_training_plan(
    session: AsyncSession,
    *,
    tenant_id: str,
    company_id: str,
    course_id: str,
    position_id: str | None = None,
    person_id: str | None = None,
    due_date: date | None = None,
    is_mandatory: bool = True,
    actor_id: str | None = None,
) -> TrainingPlan:
    """Create a training plan for a person or position within a company."""

    await _get_company(session, tenant_id, company_id)
    course = await _get_course(session, tenant_id, course_id)

    if person_id is None and position_id is None:
        raise ValueError("Either person_id or position_id must be provided")

    position: Position | None = None
    person: Person | None = None

    if position_id is not None:
        position = await _get_position(session, tenant_id, position_id)
        if position.company_id != company_id:
            raise ValueError("Position does not belong to the specified company")

    if person_id is not None:
        person = await _get_person(session, tenant_id, person_id)
        if person.company_id != company_id:
            raise ValueError("Person does not belong to the specified company")

    plan = TrainingPlan(
        tenant_id=tenant_id,
        company_id=company_id,
        position_id=position.id if position else None,
        person_id=person.id if person else None,
        course_id=course.id,
        due_date=due_date,
        is_mandatory=is_mandatory,
    )
    session.add(plan)
    await session.flush()
    await session.refresh(plan)
    await create_training_task(
        session,
        tenant_id=tenant_id,
        plan=plan,
        course=course,
        actor_id=actor_id,
    )
    outbox = OutboxService(session)
    await outbox.enqueue(
        tenant_id=tenant_id,
        event_type=EventType.TRAINING_ASSIGNED.value,
        payload={
            "tenant_id": tenant_id,
            "actor_id": actor_id,
            "occurred_at": plan.assigned_at,
            "training_event_id": plan.id,
            "plan_id": plan.id,
            "company_id": plan.company_id,
            "course_id": plan.course_id,
            "position_id": plan.position_id,
            "person_id": plan.person_id,
            "due_date": plan.due_date,
            "is_mandatory": plan.is_mandatory,
            "assigned_at": plan.assigned_at,
        },
    )
    return plan


async def register_training_session(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_id: str,
    course_id: str,
    plan_id: str | None = None,
    status: TrainingSessionStatus = TrainingSessionStatus.COMPLETED,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    score: int | None = None,
    notes: str | None = None,
) -> TrainingSession:
    """Register a training session attempt for a person."""

    person = await _get_person(session, tenant_id, person_id)
    course = await _get_course(session, tenant_id, course_id)
    plan: TrainingPlan | None = None

    if plan_id is not None:
        plan = await _get_plan(session, tenant_id, plan_id)
        if plan.course_id != course.id or (plan.person_id and plan.person_id != person.id):
            raise ValueError("Plan does not match person or course")

    now = datetime.now(tz=timezone.utc)
    started_value = started_at or (now if status in {TrainingSessionStatus.IN_PROGRESS, TrainingSessionStatus.COMPLETED} else None)
    completed_value = completed_at or (now if status == TrainingSessionStatus.COMPLETED else None)

    record = TrainingSession(
        tenant_id=tenant_id,
        person_id=person.id,
        course_id=course.id,
        plan_id=plan.id if plan else None,
        status=status,
        started_at=started_value,
        completed_at=completed_value,
        score=score,
        notes=notes,
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return record


async def issue_certificate(
    session: AsyncSession,
    *,
    tenant_id: str,
    person_id: str,
    course_id: str,
    plan_id: str | None = None,
    session_id: str | None = None,
    file_id: str | None = None,
    number: str | None = None,
    issued_at: date | None = None,
    valid_until: date | None = None,
    permit_type: str | None = None,
    position_id: str | None = None,
) -> TrainingCertificateIssueResult:
    """Issue a training certificate and optionally generate a permit."""

    person = await _get_person(session, tenant_id, person_id)
    course = await _get_course(session, tenant_id, course_id)
    plan: TrainingPlan | None = None
    training_session: TrainingSession | None = None
    file: File | None = None

    if plan_id:
        plan = await _get_plan(session, tenant_id, plan_id)

    if session_id:
        training_session = await _get_training_session(session, tenant_id, session_id)

    if file_id:
        file = await _get_file(session, tenant_id, file_id)

    computed_issued_at = issued_at or date.today()
    if valid_until is None and course.valid_period_days:
        valid_until = computed_issued_at + timedelta(days=int(course.valid_period_days))

    certificate = TrainingCertificate(
        tenant_id=tenant_id,
        person_id=person.id,
        course_id=course.id,
        plan_id=plan.id if plan else None,
        session_id=training_session.id if training_session else None,
        file_id=file.id if file else None,
        number=number,
        issued_at=computed_issued_at,
        valid_until=valid_until,
    )
    session.add(certificate)
    await session.flush()
    await session.refresh(certificate)

    permit: Permit | None = None
    normalized_permit_type = permit_type or course.title
    if normalized_permit_type:
        permit = Permit(
            tenant_id=tenant_id,
            person_id=person.id,
            position_id=position_id or person.position_id,
            permit_type=normalized_permit_type,
            issued_at=computed_issued_at,
            valid_until=valid_until,
            status=PermitStatus.ACTIVE.value if (valid_until is None or valid_until >= computed_issued_at) else PermitStatus.EXPIRED.value,
        )
        session.add(permit)
        await session.flush()
        await session.refresh(permit)

    return TrainingCertificateIssueResult(certificate=certificate, permit=permit)


async def _get_file(session: AsyncSession, tenant_id: str, file_id: str) -> File:
    stmt = select(File).where(File.id == file_id, File.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one()


async def _get_training_session(
    session: AsyncSession, tenant_id: str, session_id: str
) -> TrainingSession:
    stmt = select(TrainingSession).where(
        TrainingSession.id == session_id,
        TrainingSession.tenant_id == tenant_id,
    )
    return (await session.execute(stmt)).scalar_one()


async def upcoming_certificate_expirations(
    session: AsyncSession,
    *,
    tenant_id: str,
    before: date | None = None,
) -> Iterable[TrainingCertificate]:
    """Return certificates that expire before or on the provided date."""

    cutoff = before or (date.today() + timedelta(days=30))
    stmt = select(TrainingCertificate).where(
        TrainingCertificate.tenant_id == tenant_id,
        TrainingCertificate.deleted_at.is_(None),
        TrainingCertificate.valid_until.is_not(None),
        TrainingCertificate.valid_until <= cutoff,
    )
    result = await session.execute(stmt)
    return result.scalars().all()
