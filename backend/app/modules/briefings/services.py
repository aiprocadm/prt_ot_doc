from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BriefingEntry, BriefingSignature, BriefingTemplate
from app.services.events import EventType
from app.services.outbox import OutboxService
from app.services.pep_signing import PepSigningService


class BriefingEntryService:
    async def sign(
        self,
        session: AsyncSession,
        entry: BriefingEntry,
        signer_type: str,
        signer_user_id: str | None,
        *,
        signature_payload: dict[str, Any] | None = None,
    ) -> BriefingSignature:
        existing = (
            await session.execute(
                select(BriefingSignature).where(
                    BriefingSignature.briefing_entry_id == entry.id,
                    BriefingSignature.signer_type == signer_type,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if signer_user_id and existing.signer_user_id != signer_user_id:
                existing.signer_user_id = signer_user_id
            if signature_payload:
                existing.signature_payload = {**(existing.signature_payload or {}), **signature_payload}
            await session.flush()
            return existing

        # Для employee подписант — person записи; для instructor — signer_user_id.
        # Fallback реализован: если signer_type=="employee" и entry.person_id is None,
        # подпись фиксируется за user-оформителем (signer_user_id); если и он None —
        # PEP-запись создаётся без указания подписанта (допустимо для attested-режима).
        employee_person_id = entry.person_id if signer_type == "employee" else None
        pep_signer_user_id = (
            signer_user_id
            if signer_type == "instructor" or employee_person_id is None
            else None
        )
        pep_req = await PepSigningService(session, str(entry.tenant_id)).create_attested(
            object_type="briefing_entry",
            object_id=entry.id,
            purpose="briefing",
            requested_by=signer_user_id or "system",
            signer_user_id=pep_signer_user_id,
            signer_person_id=employee_person_id,
        )
        signature = BriefingSignature(
            tenant_id=entry.tenant_id,
            briefing_entry_id=entry.id,
            signer_type=signer_type,
            signer_user_id=signer_user_id,
            signature_mode="internal_simple",
            signature_payload={**(signature_payload or {}), "pep_request_id": pep_req.id},
        )
        session.add(signature)
        entry.status = "signed_employee" if signer_type == "employee" else "signed_instructor"
        await session.flush()
        return signature

    async def complete(self, session: AsyncSession, entry: BriefingEntry) -> BriefingEntry:
        rows = (await session.execute(select(BriefingSignature.signer_type).where(BriefingSignature.briefing_entry_id == entry.id))).scalars().all()
        if "employee" not in rows or "instructor" not in rows:
            raise ValueError("Both signatures are required")
        if entry.briefing_template_id:
            template = await session.get(BriefingTemplate, entry.briefing_template_id)
            if (
                template
                and str(template.tenant_id) == str(entry.tenant_id)
                and template.validity_days
            ):
                entry.valid_until = entry.briefing_date + timedelta(days=template.validity_days)
        entry.status = "completed"
        await session.flush()
        return entry

    async def list_overdue(self, session: AsyncSession, *, tenant_id: str, now: datetime | None = None) -> list[BriefingEntry]:
        resolved_now = now or datetime.now(timezone.utc)
        stmt = select(BriefingEntry).where(
            BriefingEntry.tenant_id == tenant_id,
            BriefingEntry.deleted_at.is_(None),
            BriefingEntry.valid_until.is_not(None),
            BriefingEntry.valid_until < resolved_now,
            BriefingEntry.status != "completed",
        )
        return list((await session.execute(stmt.order_by(BriefingEntry.valid_until.asc()))).scalars().all())

    async def notify_overdue(
        self,
        session: AsyncSession,
        *,
        tenant_id: str,
        actor_id: str | None = None,
        now: datetime | None = None,
    ) -> list[BriefingEntry]:
        overdue = await self.list_overdue(session, tenant_id=tenant_id, now=now)
        if not overdue:
            return []
        outbox = OutboxService(session)
        for entry in overdue:
            due_at = entry.valid_until or entry.briefing_date
            await outbox.enqueue(
                tenant_id=tenant_id,
                event_type=EventType.TASK_OVERDUE.value,
                idempotency_key=f"briefing-overdue:{entry.id}:{due_at.date().isoformat()}",
                payload={
                    "tenant_id": tenant_id,
                    "actor_id": actor_id,
                    "task_id": entry.id,
                    "title": f"Briefing overdue: {entry.briefing_type}",
                    "due_at": due_at,
                    "assignee_id": entry.person_id,
                    "status": entry.status,
                    "priority": "high",
                    "overdue": True,
                },
            )
        return overdue
