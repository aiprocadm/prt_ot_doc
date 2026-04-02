from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.headers.models import HeaderFooterPreset


async def get_preset_by_code(session: AsyncSession, *, tenant_id: str, code: str) -> HeaderFooterPreset | None:
    stmt = select(HeaderFooterPreset).where(
        HeaderFooterPreset.tenant_id == tenant_id,
        HeaderFooterPreset.code == code,
        HeaderFooterPreset.deleted_at.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()
