from __future__ import annotations

import calendar
from datetime import date, datetime, timezone

from app.models.models import (
    TrainingAttempt,
    TrainingCertificate,
    TrainingEnrollment,
    TrainingLesson,
    TrainingModule,
    TrainingProgram,
    TrainingTest,
)
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


class TrainingEnrollmentService:
    @staticmethod
    def _add_months(value: datetime, months: int) -> datetime:
        target_month = value.month - 1 + months
        year = value.year + target_month // 12
        month = target_month % 12 + 1
        day = min(value.day, calendar.monthrange(year, month)[1])
        return value.replace(year=year, month=month, day=day)

    async def start(self, session: AsyncSession, enrollment: TrainingEnrollment) -> TrainingEnrollment:
        enrollment.status = "in_progress"
        enrollment.completion_status = "in_progress"
        enrollment.started_at = enrollment.started_at or datetime.now(tz=timezone.utc)
        await session.flush()
        return enrollment

    async def update_progress(
        self,
        session: AsyncSession,
        enrollment: TrainingEnrollment,
        *,
        completed_lesson_ids: list[str] | None = None,
        progress_percent: float | None = None,
        runtime_state: dict | None = None,
    ) -> TrainingEnrollment:
        if progress_percent is None:
            module_ids = (
                await session.execute(
                    select(TrainingModule.id).where(
                        TrainingModule.training_program_id == enrollment.training_program_id,
                        TrainingModule.tenant_id == enrollment.tenant_id,
                    )
                )
            ).scalars().all()
            lesson_total = (
                await session.execute(
                    select(func.count())
                    .select_from(TrainingLesson)
                    .where(
                        TrainingLesson.tenant_id == enrollment.tenant_id,
                        TrainingLesson.training_module_id.in_(module_ids or ["__none__"]),
                    )
                )
            ).scalar_one()
            completed = len(set(completed_lesson_ids or []))
            progress_percent = 100.0 if lesson_total == 0 else round(min(100.0, (completed / lesson_total) * 100), 2)
        enrollment.progress_percent = progress_percent
        if runtime_state:
            enrollment.external_runtime_state = {
                **(enrollment.external_runtime_state or {}),
                **runtime_state,
            }
        if progress_percent > 0 and enrollment.status == "assigned":
            enrollment.status = "in_progress"
            enrollment.completion_status = "in_progress"
            enrollment.started_at = enrollment.started_at or datetime.now(tz=timezone.utc)
        await session.flush()
        return enrollment

    async def submit_attempt(
        self,
        session: AsyncSession,
        enrollment: TrainingEnrollment,
        answers_json: dict,
        *,
        source_type: str = "manual",
        external_session_ref: str | None = None,
        provider_payload: dict | None = None,
    ) -> TrainingAttempt:
        score = float(answers_json.get("score", 0))
        passed = bool(answers_json.get("passed", False))
        test_stmt = select(TrainingTest).where(
            TrainingTest.training_program_id == enrollment.training_program_id,
            TrainingTest.tenant_id == enrollment.tenant_id,
            TrainingTest.deleted_at.is_(None),
        )
        test = (await session.execute(test_stmt)).scalar_one_or_none()
        if test is not None and test.attempts_limit is not None and enrollment.attempt_count >= test.attempts_limit:
            raise ValueError("attempts_limit_exceeded")
        if test is not None:
            passed = score >= test.passing_score
        enrollment.attempt_count += 1
        enrollment.score = score
        if passed:
            enrollment.status = "passed"
            enrollment.completion_status = "completed"
            enrollment.progress_percent = 100
            enrollment.completed_at = datetime.now(tz=timezone.utc)
            program = await session.get(TrainingProgram, enrollment.training_program_id)
            if program and program.validity_months:
                enrollment.expires_at = self._add_months(enrollment.completed_at, program.validity_months).replace(microsecond=0)
        else:
            enrollment.status = "failed"
            enrollment.completion_status = "retake_required"

        attempt = TrainingAttempt(
            tenant_id=enrollment.tenant_id,
            training_enrollment_id=enrollment.id,
            started_at=enrollment.started_at,
            submitted_at=datetime.now(tz=timezone.utc),
            score=score,
            passed=passed,
            answers_json=answers_json,
            source_type=source_type,
            external_session_ref=external_session_ref,
            provider_payload=provider_payload,
        )
        session.add(attempt)
        await session.flush()
        return attempt

    async def confirm_completion(
        self,
        session: AsyncSession,
        enrollment: TrainingEnrollment,
        *,
        confirmed_by: str | None,
        payload: dict | None = None,
    ) -> TrainingEnrollment:
        enrollment.status = "completed"
        enrollment.completion_status = "confirmed"
        enrollment.progress_percent = 100
        now = datetime.now(tz=timezone.utc)
        enrollment.completed_at = enrollment.completed_at or now
        enrollment.completion_confirmed_at = now
        enrollment.completion_payload = {"confirmed_by": confirmed_by, **(payload or {})}
        await session.flush()
        return enrollment


class TrainingCertificateService:
    async def next_code(self, session: AsyncSession, tenant_id: str) -> str:
        count_stmt = select(func.count()).select_from(TrainingCertificate).where(
            TrainingCertificate.tenant_id == tenant_id
        )
        count = (await session.execute(count_stmt)).scalar_one()
        return f"CERT-{date.today():%Y%m%d}-{count + 1:05d}"
