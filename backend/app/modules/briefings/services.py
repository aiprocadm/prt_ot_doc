from __future__ import annotations

from datetime import timedelta

from app.models.models import BriefingEntry, BriefingSignature, BriefingTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class BriefingEntryService:
    async def sign(self, session: AsyncSession, entry: BriefingEntry, signer_type: str, signer_user_id: str | None) -> BriefingSignature:
        signature = BriefingSignature(
            tenant_id=entry.tenant_id,
            briefing_entry_id=entry.id,
            signer_type=signer_type,
            signer_user_id=signer_user_id,
            signature_mode="internal_simple",
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
            if template and template.validity_days:
                entry.valid_until = entry.briefing_date + timedelta(days=template.validity_days)
        entry.status = "completed"
        await session.flush()
        return entry
