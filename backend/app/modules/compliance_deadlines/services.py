from __future__ import annotations

from datetime import datetime, timezone

from app.models.models import ComplianceDeadline, TrainingCertificate
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession


class ComplianceDeadlineService:
    async def recompute_for_certificates(self, session: AsyncSession, tenant_id: str) -> int:
        await session.execute(delete(ComplianceDeadline).where(ComplianceDeadline.tenant_id == tenant_id, ComplianceDeadline.entity_type == "training_certificate"))
        now = datetime.now(tz=timezone.utc)
        count = 0
        rows = (await session.execute(
            TrainingCertificate.__table__.select().where(TrainingCertificate.tenant_id == tenant_id, TrainingCertificate.deleted_at.is_(None))
        )).mappings().all()
        for row in rows:
            if row["valid_until"] is None:
                continue
            due_dt = datetime.combine(row["valid_until"], datetime.min.time(), tzinfo=timezone.utc)
            status = "overdue" if due_dt < now else "upcoming"
            session.add(ComplianceDeadline(tenant_id=tenant_id, entity_type="training_certificate", entity_id=row["id"], person_id=row["person_id"], due_at=due_dt, status=status))
            count += 1
        await session.flush()
        return count
