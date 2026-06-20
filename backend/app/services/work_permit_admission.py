"""Brigade-readiness gate for issuing a work permit (наряд-допуск).

Blocks issuance when a brigade member has an expired/absent personal permit,
or an expired medical exam / training certificate. Absent medical/training is a
warning (not a block). Reuses the Срез-1 personal-permit lifecycle.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.permits import lifecycle as plc
from app.models.models import MedicalExam, Permit, TrainingCertificate
from app.models.work_permit import WorkPermitMember


@dataclass(slots=True)
class MemberViolation:
    person_id: str
    role: str
    code: str
    severity: str  # "block" | "warn"


@dataclass(slots=True)
class ReadinessReport:
    ok: bool
    violations: list[MemberViolation]


class WorkPermitBlocked(Exception):
    """Raised on issue when at least one brigade member is blocked (→ HTTP 409)."""

    def __init__(self, violations: list[MemberViolation]) -> None:
        self.violations = violations
        super().__init__("work permit blocked: brigade readiness failed")


def _today() -> date:
    return date.today()


async def _member_violations(
    session: AsyncSession, tenant_id: str, person_id: str, role: str
) -> list[MemberViolation]:
    today = _today()
    out: list[MemberViolation] = []

    permits = (await session.execute(
        select(Permit).where(Permit.tenant_id == tenant_id, Permit.person_id == person_id)
    )).scalars().all()
    has_active_valid = any(
        p.status == plc.PERMIT_STATUS_ACTIVE
        and not plc.is_expired(str(p.status), p.valid_until, today)
        for p in permits
    )
    if not has_active_valid:
        out.append(MemberViolation(
            person_id, role,
            "permit_expired" if permits else "permit_missing", "block",
        ))

    exams = (await session.execute(
        select(MedicalExam).where(
            MedicalExam.tenant_id == tenant_id, MedicalExam.person_id == person_id,
            MedicalExam.deleted_at.is_(None),
        ).order_by(MedicalExam.exam_date.desc())
    )).scalars().all()
    if not exams:
        out.append(MemberViolation(person_id, role, "medical_absent", "warn"))
    elif exams[0].valid_until < today:
        out.append(MemberViolation(person_id, role, "medical_expired", "block"))

    certs = (await session.execute(
        select(TrainingCertificate).where(
            TrainingCertificate.tenant_id == tenant_id,
            TrainingCertificate.person_id == person_id,
            TrainingCertificate.deleted_at.is_(None),
        )
    )).scalars().all()
    if not certs:
        out.append(MemberViolation(person_id, role, "training_absent", "warn"))
    elif not any(c.valid_until is None or c.valid_until >= today for c in certs):
        out.append(MemberViolation(person_id, role, "training_expired", "block"))

    return out


async def check_brigade_readiness(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str
) -> ReadinessReport:
    members = (await session.execute(
        select(WorkPermitMember).where(
            WorkPermitMember.tenant_id == tenant_id,
            WorkPermitMember.work_permit_id == work_permit_id,
        )
    )).scalars().all()
    violations: list[MemberViolation] = []
    for m in members:
        violations.extend(await _member_violations(session, tenant_id, m.person_id, m.role))
    ok = not any(v.severity == "block" for v in violations)
    return ReadinessReport(ok=ok, violations=violations)


async def enforce_brigade_readiness(
    session: AsyncSession, *, tenant_id: str, work_permit_id: str
) -> None:
    report = await check_brigade_readiness(
        session, tenant_id=tenant_id, work_permit_id=work_permit_id
    )
    if not report.ok:
        raise WorkPermitBlocked([v for v in report.violations if v.severity == "block"])
