from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BriefingEntry, OfflineMediaQueue, OfflineSyncBatch


class OfflineSyncService:
    async def apply_batch(self, session: AsyncSession, batch: OfflineSyncBatch) -> OfflineSyncBatch:
        payload = batch.payload or {}
        entity_type = payload.get("entity_type")
        if entity_type == "briefing_entry":
            entry_id = payload.get("id")
            entry = await session.get(BriefingEntry, entry_id) if entry_id else None
            if entry and entry.status in {"completed", "signed_employee", "signed_instructor"}:
                batch.status = "failed"
                batch.error_payload = {"error": "conflict_final_record"}
            else:
                batch.status = "applied"
        else:
            batch.status = "applied"
        await session.flush()
        return batch

    async def commit_media(self, session: AsyncSession, media: OfflineMediaQueue) -> OfflineMediaQueue:
        media.upload_status = "uploaded"
        await session.flush()
        return media

    async def get_status(self, session: AsyncSession, batch_id: str) -> OfflineSyncBatch | None:
        stmt = select(OfflineSyncBatch).where(OfflineSyncBatch.id == batch_id)
        return (await session.execute(stmt)).scalar_one_or_none()
