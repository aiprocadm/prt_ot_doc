from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import BriefingEntry, OfflineMediaQueue, OfflineSyncBatch


class OfflineSyncService:
    async def _latest_evidence_batch(
        self, session: AsyncSession, *, tenant_id: str, evidence_case_id: str
    ) -> OfflineSyncBatch | None:
        stmt = (
            select(OfflineSyncBatch)
            .where(
                OfflineSyncBatch.tenant_id == tenant_id,
                OfflineSyncBatch.entity_type == "evidence_case",
                OfflineSyncBatch.status == "applied",
            )
            .order_by(OfflineSyncBatch.updated_at.desc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        for row in rows:
            payload = row.payload or {}
            if str(payload.get("evidence_case_id") or "") == evidence_case_id:
                return row
        return None

    async def _apply_evidence_case_batch(self, session: AsyncSession, batch: OfflineSyncBatch) -> None:
        payload = batch.payload or {}
        operation = str(payload.get("operation") or "create")
        evidence_case_id = str(payload.get("evidence_case_id") or payload.get("id") or "")
        if not evidence_case_id:
            batch.status = "failed"
            batch.error_payload = {
                "error": "validation_missing_evidence_case_id",
                "entity": "evidence_case",
            }
            return

        latest = await self._latest_evidence_batch(
            session,
            tenant_id=str(batch.tenant_id),
            evidence_case_id=evidence_case_id,
        )
        if operation == "create" and latest is not None:
            batch.status = "failed"
            batch.error_payload = {
                "error": "conflict_evidence_case_exists",
                "entity": "evidence_case",
                "conflict_type": "create",
                "evidence_case_id": evidence_case_id,
                "resolution": "manual_review",
            }
            return

        if operation == "update":
            if latest is None:
                batch.status = "failed"
                batch.error_payload = {
                    "error": "conflict_evidence_case_missing",
                    "entity": "evidence_case",
                    "conflict_type": "update",
                    "evidence_case_id": evidence_case_id,
                    "resolution": "manual_review",
                }
                return
            client_base_version = int(payload.get("base_version") or 0)
            server_version = int((latest.payload or {}).get("version") or 1)
            if client_base_version and client_base_version != server_version:
                batch.status = "failed"
                batch.error_payload = {
                    "error": "conflict_evidence_case_version_mismatch",
                    "entity": "evidence_case",
                    "conflict_type": "update",
                    "evidence_case_id": evidence_case_id,
                    "client_base_version": client_base_version,
                    "server_version": server_version,
                    "resolution": "manual_review",
                }
                return

        next_version = 1
        if latest is not None:
            next_version = int((latest.payload or {}).get("version") or 1) + 1
        payload["version"] = next_version
        payload["synced_at"] = datetime.now(timezone.utc).isoformat()
        batch.payload = payload
        batch.status = "applied"

    async def apply_batch(self, session: AsyncSession, batch: OfflineSyncBatch) -> OfflineSyncBatch:
        payload = batch.payload or {}
        entity_type = payload.get("entity_type") or batch.entity_type
        if entity_type == "briefing_entry":
            entry_id = payload.get("id")
            entry = await session.get(BriefingEntry, entry_id) if entry_id else None
            if entry is not None and str(entry.tenant_id) != str(batch.tenant_id):
                batch.status = "failed"
                batch.error_payload = {"error": "tenant_scope_mismatch", "entity": "briefing_entry"}
            elif entry and entry.status in {"completed", "signed_employee", "signed_instructor"}:
                batch.status = "failed"
                batch.error_payload = {"error": "conflict_final_record"}
            else:
                batch.status = "applied"
        elif entity_type == "evidence_case":
            await self._apply_evidence_case_batch(session, batch)
        else:
            batch.status = "applied"
        await session.flush()
        return batch

    async def resolve_conflict(
        self,
        session: AsyncSession,
        *,
        batch: OfflineSyncBatch,
        strategy: str,
        payload_patch: dict[str, Any] | None = None,
    ) -> OfflineSyncBatch:
        if batch.status != "failed":
            return batch

        if strategy == "server_wins":
            batch.status = "applied"
            details = dict(batch.error_payload or {})
            details["resolved_by"] = "server_wins"
            details["resolved_at"] = datetime.now(timezone.utc).isoformat()
            batch.error_payload = details
        elif strategy == "client_retry":
            payload = dict(batch.payload or {})
            if payload_patch:
                payload.update(payload_patch)
            batch.payload = payload
            batch.status = "pending"
            details = dict(batch.error_payload or {})
            details["resolved_by"] = "client_retry"
            details["resolved_at"] = datetime.now(timezone.utc).isoformat()
            batch.error_payload = details
        else:
            raise ValueError("unsupported_resolution_strategy")
        await session.flush()
        return batch

    async def commit_media(self, session: AsyncSession, media: OfflineMediaQueue) -> OfflineMediaQueue:
        media.upload_status = "uploaded"
        await session.flush()
        return media

    async def get_status(
        self, session: AsyncSession, batch_id: str, *, tenant_id: str | None = None
    ) -> OfflineSyncBatch | None:
        stmt = select(OfflineSyncBatch).where(OfflineSyncBatch.id == batch_id)
        if tenant_id is not None:
            stmt = stmt.where(OfflineSyncBatch.tenant_id == tenant_id)
        return (await session.execute(stmt)).scalar_one_or_none()
