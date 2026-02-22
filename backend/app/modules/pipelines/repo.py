from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pipelines.models import PipelineProfile
from app.modules.pipelines.schemas import PipelineProfileCreate, PipelineProfilePatch


class PipelineProfileRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, *, tenant_id: str, payload: PipelineProfileCreate) -> PipelineProfile:
        model = PipelineProfile(
            tenant_id=tenant_id,
            code=payload.code,
            name=payload.name,
            steps=[s.model_dump() for s in payload.steps],
            limits=payload.limits.model_dump(),
            is_active=payload.is_active,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def list(self, *, tenant_id: str, active: bool | None = None) -> list[PipelineProfile]:
        stmt = select(PipelineProfile).where(PipelineProfile.tenant_id == tenant_id, PipelineProfile.deleted_at.is_(None))
        if active is not None:
            stmt = stmt.where(PipelineProfile.is_active.is_(active))
        return (await self.session.execute(stmt.order_by(PipelineProfile.updated_at.desc()))).scalars().all()

    async def get(self, *, tenant_id: str, profile_id: str) -> PipelineProfile | None:
        return (
            await self.session.execute(
                select(PipelineProfile).where(
                    PipelineProfile.tenant_id == tenant_id,
                    PipelineProfile.id == profile_id,
                    PipelineProfile.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def get_by_code(self, *, tenant_id: str, code: str) -> PipelineProfile | None:
        return (
            await self.session.execute(
                select(PipelineProfile).where(
                    PipelineProfile.tenant_id == tenant_id,
                    PipelineProfile.code == code,
                    PipelineProfile.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()

    async def patch(self, *, model: PipelineProfile, payload: PipelineProfilePatch) -> PipelineProfile:
        data = payload.model_dump(exclude_none=True)
        if "steps" in data:
            data["steps"] = [s.model_dump() for s in payload.steps or []]
        if "limits" in data and payload.limits:
            data["limits"] = payload.limits.model_dump()
        for key, value in data.items():
            setattr(model, key, value)
        await self.session.flush()
        return model

    async def soft_delete(self, *, model: PipelineProfile) -> None:
        model.deleted_at = datetime.now(timezone.utc)
        model.is_active = False
        await self.session.flush()
