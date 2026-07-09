from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import ComplianceDeadline, TrainingCertificate


class ComplianceDeadlineService:
    async def recompute_for_certificates(self, session: AsyncSession, tenant_id: str) -> int:
        await session.execute(
            delete(ComplianceDeadline).where(
                ComplianceDeadline.tenant_id == tenant_id,
                ComplianceDeadline.entity_type == "training_certificate",
            )
        )
        now = datetime.now(tz=timezone.utc)
        count = 0
        rows = (
            (
                await session.execute(
                    TrainingCertificate.__table__.select().where(
                        TrainingCertificate.tenant_id == tenant_id,
                        TrainingCertificate.deleted_at.is_(None),
                    )
                )
            )
            .mappings()
            .all()
        )
        for row in rows:
            if row["valid_until"] is None:
                continue
            due_dt = datetime.combine(row["valid_until"], datetime.min.time(), tzinfo=timezone.utc)
            # Compare on date grain: a certificate whose valid_until is today is still
            # valid for all of today, so it is not overdue until tomorrow (matches the
            # medical-exam `valid_until < today` reference semantics).
            status = "overdue" if row["valid_until"] < now.date() else "upcoming"
            session.add(
                ComplianceDeadline(
                    tenant_id=tenant_id,
                    entity_type="training_certificate",
                    entity_id=row["id"],
                    person_id=row["person_id"],
                    due_at=due_dt,
                    status=status,
                )
            )
            count += 1
        await session.flush()
        return count
