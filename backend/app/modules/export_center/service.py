from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.projections.models import ExportJob


class ExportCenterService:
    def __init__(self, session: AsyncSession, tenant_id: str) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def create_job(self, *, export_type: str, scope_json: dict[str, Any], filters_json: dict[str, Any], idempotency_key: str | None) -> ExportJob:
        if idempotency_key:
            existing = (
                await self.session.execute(
                    select(ExportJob).where(
                        ExportJob.tenant_id == self.tenant_id,
                        ExportJob.export_type == export_type,
                        ExportJob.scope_json == scope_json,
                        ExportJob.filters_json == filters_json,
                        ExportJob.status.in_(["queued", "running", "done"]),
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                return existing

        job = ExportJob(
            tenant_id=self.tenant_id,
            export_type=export_type,
            scope_json=scope_json,
            filters_json=filters_json,
            status="queued",
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        return job
