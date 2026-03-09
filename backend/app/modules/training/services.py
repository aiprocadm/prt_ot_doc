from __future__ import annotations

from datetime import date, datetime, timezone

from app.models.models import (
    TrainingAttempt,
    TrainingCertificate,
    TrainingEnrollment,
    TrainingProgram,
    TrainingTest,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class TrainingEnrollmentService:
    async def start(self, session: AsyncSession, enrollment: TrainingEnrollment) -> TrainingEnrollment:
        enrollment.status = "in_progress"
        enrollment.started_at = enrollment.started_at or datetime.now(tz=timezone.utc)
        await session.flush()
        return enrollment

    async def submit_attempt(
        self,
        session: AsyncSession,
        enrollment: TrainingEnrollment,
        answers_json: dict,
    ) -> TrainingAttempt:
        score = float(answers_json.get("score", 0))
        passed = bool(answers_json.get("passed", False))
        test_stmt = select(TrainingTest).where(
            TrainingTest.training_program_id == enrollment.training_program_id,
            TrainingTest.tenant_id == enrollment.tenant_id,
            TrainingTest.deleted_at.is_(None),
        )
        test = (await session.execute(test_stmt)).scalar_one_or_none()
        if test is not None:
            passed = score >= test.passing_score
        enrollment.attempt_count += 1
        enrollment.score = score
        if passed:
            enrollment.status = "passed"
            enrollment.completed_at = datetime.now(tz=timezone.utc)
            program = await session.get(TrainingProgram, enrollment.training_program_id)
            if program and program.validity_months:
                enrollment.expires_at = datetime.now(tz=timezone.utc).replace(microsecond=0)
        else:
            enrollment.status = "failed"

        attempt = TrainingAttempt(
            tenant_id=enrollment.tenant_id,
            training_enrollment_id=enrollment.id,
            started_at=enrollment.started_at,
            submitted_at=datetime.now(tz=timezone.utc),
            score=score,
            passed=passed,
            answers_json=answers_json,
        )
        session.add(attempt)
        await session.flush()
        return attempt


class TrainingCertificateService:
    async def next_code(self, session: AsyncSession, tenant_id: str) -> str:
        count_stmt = select(func.count()).select_from(TrainingCertificate).where(
            TrainingCertificate.tenant_id == tenant_id
        )
        count = (await session.execute(count_stmt)).scalar_one()
        return f"CERT-{date.today():%Y%m%d}-{count + 1:05d}"
