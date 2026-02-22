from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.replace.models import ReplaceMap, ReplaceRun


async def get_replace_map_by_code(session: AsyncSession, *, tenant_id: str, code: str) -> ReplaceMap | None:
    return (
        await session.execute(
            select(ReplaceMap).where(
                ReplaceMap.tenant_id == tenant_id,
                ReplaceMap.code == code,
                ReplaceMap.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def list_replace_maps(session: AsyncSession, *, tenant_id: str) -> list[ReplaceMap]:
    return (
        await session.execute(
            select(ReplaceMap)
            .where(ReplaceMap.tenant_id == tenant_id, ReplaceMap.deleted_at.is_(None))
            .order_by(ReplaceMap.updated_at.desc())
        )
    ).scalars().all()


async def get_replace_run(session: AsyncSession, *, tenant_id: str, run_id: str) -> ReplaceRun | None:
    row = await session.get(ReplaceRun, run_id)
    if row is None or row.tenant_id != tenant_id:
        return None
    return row
