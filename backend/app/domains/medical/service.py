"""Medical domain I/O service (TZ B.8)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domains.medical import lifecycle as lc
from app.models.models import (
    MedicalExam, MedicalExamKind, MedicalFactor, MedicalFitness, MedicalNorm,
    MedicalReferral, MedicalReferralStatus, MedicalSuspension,
    MedicalSuspensionStatus, Person, Position,
)
from app.services.events import EventType
from app.services.outbox import OutboxService


async def list_active_suspensions(
    session: AsyncSession, *, tenant_id: str, person_ids: list[str]
) -> list[MedicalSuspension]:
    """Active (not lifted, not deleted) suspensions for the given persons, tenant-scoped."""
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
    """Periodicity in days for (person's position, exam_kind): the matching norm's interval, else the per-kind default."""
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
    """Record an exam result; compute valid_until from norms if absent; emit MedicalExamRecorded; open/lift a suspension per the fitness verdict. Does not commit."""
    person = (await session.execute(
        select(Person).where(
            Person.id == person_id, Person.tenant_id == tenant_id, Person.deleted_at.is_(None)
        )
    )).scalar_one_or_none()
    if person is None:
        raise ValueError(f"person not found: {person_id}")

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
                                person_id=person_id, exam=exam, fitness=fitness, outbox=outbox)
    return exam


async def _apply_suspension(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, person_id: str,
    exam: MedicalExam, fitness: MedicalFitness, outbox: OutboxService,
) -> None:
    """Open a suspension when the verdict is UNFIT (no active one), or lift active ones when fit again — per lc.suspension_action."""
    actives = await list_active_suspensions(session, tenant_id=tenant_id, person_ids=[person_id])
    action = lc.suspension_action(bool(actives), fitness)
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
        now = datetime.now(tz=timezone.utc)
        for susp in actives:
            susp.status = MedicalSuspensionStatus.LIFTED
            susp.lifted_at = now
            susp.lifted_by = actor_id
        await session.flush()
        for susp in actives:
            await outbox.enqueue(
                tenant_id=tenant_id, event_type=EventType.PERSON_REINSTATED.value,
                idempotency_key=f"person-reinstated:{susp.id}",
                payload={"tenant_id": tenant_id, "actor_id": actor_id,
                         "suspension_id": susp.id, "person_id": person_id},
            )


async def update_exam(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, exam_id: str,
    fitness: MedicalFitness | None = None, conclusion: str | None = None,
    restrictions: str | None = None, contraindications: list[str] | None = None,
    valid_until: date | None = None,
) -> MedicalExam:
    """Edit an exam's result fields; if fitness is changed, re-run the suspension safety loop. Does not commit."""
    exam = (await session.execute(select(MedicalExam).where(
        MedicalExam.id == exam_id, MedicalExam.tenant_id == tenant_id,
        MedicalExam.deleted_at.is_(None)))).scalar_one_or_none()
    if exam is None:
        raise ValueError(f"exam not found: {exam_id}")
    if conclusion is not None:
        exam.conclusion = conclusion
    if restrictions is not None:
        exam.restrictions = restrictions
    if contraindications is not None:
        exam.contraindications = list(contraindications)
    if valid_until is not None:
        exam.valid_until = valid_until
    if fitness is not None:
        exam.fitness = fitness
    await session.flush()
    if fitness is not None:
        outbox = OutboxService(session)
        await _apply_suspension(session, tenant_id=tenant_id, actor_id=actor_id,
                                person_id=exam.person_id, exam=exam, fitness=fitness, outbox=outbox)
    return exam


# ---------------------------------------------------------------------------
# 5.2 — Contingent computation + summary
# ---------------------------------------------------------------------------


async def _load_factor_catalog(
    session: AsyncSession, *, tenant_id: str
) -> list[lc.FactorTuple]:
    """29н factor catalog as ORM-free FactorTuples for the pure engine."""
    stmt = select(
        MedicalFactor.code, MedicalFactor.name,
        MedicalFactor.exam_kinds, MedicalFactor.periodicity_months,
    ).where(MedicalFactor.tenant_id == tenant_id)
    out: list[lc.FactorTuple] = []
    for code, name, kinds, months in (await session.execute(stmt)).all():
        out.append((code, name, tuple(MedicalExamKind(k) for k in (kinds or [])), int(months)))
    return out


async def compute_contingent(
    session: AsyncSession, *, tenant_id: str, today: date, warning_days: int = 30,
    position_id: str | None = None,
) -> list[dict]:
    """Per (active person, required exam-kind) contingent rows with status (ok/due_soon/overdue/missing).

    Required kinds = norm-driven (resolve_required_kinds) ∪ factor-driven (29н factors mapped
    via Position hazards' medical_factor_code). A person enters the contingent even without a
    manual MedicalNorm when their position's hazards map to 29н factors.
    """
    norm_stmt = select(
        MedicalNorm.position_id, MedicalNorm.hazard_id,
        MedicalNorm.working_conditions_class, MedicalNorm.exam_kind,
    ).where(MedicalNorm.tenant_id == tenant_id)
    norms = [(r[0], r[1], r[2], r[3]) for r in (await session.execute(norm_stmt)).all()]
    catalog = await _load_factor_catalog(session, tenant_id=tenant_id)
    if not norms and not catalog:
        return []

    p_stmt = (
        select(Person)
        .where(
            Person.tenant_id == tenant_id, Person.deleted_at.is_(None),
            Person.position_id.is_not(None),
        )
        .options(selectinload(Person.position).selectinload(Position.hazards))
    )
    if position_id:
        p_stmt = p_stmt.where(Person.position_id == position_id)
    people = list((await session.execute(p_stmt)).scalars().all())
    if not people:
        return []

    person_ids = [p.id for p in people]
    ex_stmt = select(
        MedicalExam.person_id, MedicalExam.exam_kind, func.max(MedicalExam.valid_until),
    ).where(
        MedicalExam.tenant_id == tenant_id, MedicalExam.deleted_at.is_(None),
        MedicalExam.person_id.in_(person_ids), MedicalExam.exam_kind.is_not(None),
    ).group_by(MedicalExam.person_id, MedicalExam.exam_kind)
    latest: dict[tuple[str, MedicalExamKind], date] = {
        (pid, kind): vu for pid, kind, vu in (await session.execute(ex_stmt)).all()
    }

    items: list[dict] = []
    for person in people:
        hazards = person.position.hazards if person.position else []
        hazard_ids = {h.id for h in hazards}
        factor_codes = {h.medical_factor_code for h in hazards if h.medical_factor_code}
        required = lc.resolve_required_kinds(
            person.position_id, person.working_conditions_class, hazard_ids, norms,
        )
        required |= set(
            lc.required_exams_from_factors(
                lc.factors_for_hazards(factor_codes, catalog)
            ).keys()
        )
        for kind in required:
            vu = latest.get((person.id, kind))
            st = lc.classify(vu, today, warning_days)
            items.append({
                "person_id": person.id, "exam_kind": kind.value,
                "status": st.value, "valid_until": vu,
                "due_at": vu if vu is not None else today,
            })
    return items


async def status_summary(session: AsyncSession, *, tenant_id: str, today: date) -> dict:
    """Per-status contingent counts + overdue (overdue+missing) + active-suspension count."""
    items = await compute_contingent(session, tenant_id=tenant_id, today=today)
    by_status: dict[str, int] = {}
    for it in items:
        by_status[it["status"]] = by_status.get(it["status"], 0) + 1
    suspended = await session.scalar(
        select(func.count()).select_from(MedicalSuspension).where(
            MedicalSuspension.tenant_id == tenant_id,
            MedicalSuspension.deleted_at.is_(None),
            MedicalSuspension.status == MedicalSuspensionStatus.ACTIVE,
        )
    )
    return {
        "by_status": by_status,
        "total": len(items),
        "overdue_count": by_status.get("overdue", 0) + by_status.get("missing", 0),
        "suspended_count": int(suspended or 0),
    }


# ---------------------------------------------------------------------------
# 5.3 — Referrals + idempotent generation
# ---------------------------------------------------------------------------


async def _open_referral_kinds(
    session: AsyncSession, *, tenant_id: str, person_id: str
) -> set[MedicalExamKind]:
    """Exam kinds with a non-terminal (open) referral for the person."""
    stmt = select(MedicalReferral.exam_kind).where(
        MedicalReferral.tenant_id == tenant_id,
        MedicalReferral.deleted_at.is_(None),
        MedicalReferral.person_id == person_id,
        MedicalReferral.status.not_in(list(lc.TERMINAL_STATES)),
    )
    return set((await session.execute(stmt)).scalars().all())


async def issue_referral(
    session: AsyncSession, *, tenant_id: str, person_id: str, exam_kind: MedicalExamKind,
    due_at: date | None, medical_org_name: str | None, issued_by: str | None,
) -> MedicalReferral:
    """Create an ISSUED referral. Does not commit."""
    ref = MedicalReferral(
        tenant_id=tenant_id, person_id=person_id, exam_kind=exam_kind, due_at=due_at,
        status=MedicalReferralStatus.ISSUED, medical_org_name=medical_org_name,
        issued_by=issued_by,
    )
    session.add(ref)
    await session.flush()
    return ref


async def generate_due_referrals(
    session: AsyncSession, *, tenant_id: str, today: date, issued_by: str | None = None,
) -> int:
    """Issue ISSUED referrals for MISSING/OVERDUE required kinds lacking an open referral. Idempotent."""
    items = await compute_contingent(session, tenant_id=tenant_id, today=today)
    created = 0
    for it in items:
        if it["status"] not in ("missing", "overdue"):
            continue
        kind = MedicalExamKind(it["exam_kind"])
        open_kinds = await _open_referral_kinds(session, tenant_id=tenant_id, person_id=it["person_id"])
        if kind in open_kinds:
            continue
        await issue_referral(session, tenant_id=tenant_id, person_id=it["person_id"],
                             exam_kind=kind, due_at=today, medical_org_name=None,
                             issued_by=issued_by)
        created += 1
    return created


# ---------------------------------------------------------------------------
# 5.4 — notify_overdue
# ---------------------------------------------------------------------------


async def notify_overdue(
    session: AsyncSession, *, tenant_id: str, actor_id: str | None, today: date
) -> int:
    """Enqueue TASK_OVERDUE for overdue/missing contingent items. Idempotent per day via the key."""
    items = await compute_contingent(session, tenant_id=tenant_id, today=today)
    outbox = OutboxService(session)
    count = 0
    for it in items:
        if it["status"] not in ("overdue", "missing"):
            continue
        await outbox.enqueue(
            tenant_id=tenant_id, event_type=EventType.TASK_OVERDUE.value,
            idempotency_key=f"medical-contingent:{it['person_id']}:{it['exam_kind']}:{today.isoformat()}",
            payload={"tenant_id": tenant_id, "actor_id": actor_id,
                     "task_id": f"{it['person_id']}:{it['exam_kind']}",
                     "title": f"Медосмотр просрочен/отсутствует: {it['exam_kind']}",
                     "due_at": None, "assignee_id": None, "status": it["status"],
                     "priority": "high", "overdue": True},
        )
        count += 1
    return count
