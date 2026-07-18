from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import CalendarEvent, ComplianceDeadline


class CalendarProjectionService:
    async def project_deadline(self, session: AsyncSession, deadline: ComplianceDeadline) -> CalendarEvent:
        event = CalendarEvent(
            tenant_id=deadline.tenant_id,
            source_type="compliance_deadline",
            source_id=deadline.id,
            title=f"Deadline: {deadline.entity_type}",
            starts_at=deadline.due_at,
            status="active",
        )
        session.add(event)
        await session.flush()
        return event
