from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.pdf.models import PdfConversionRun


async def find_run_by_input(
    session: AsyncSession, *, tenant_id: str, input_file_id: str
) -> PdfConversionRun | None:
    stmt = (
        select(PdfConversionRun)
        .where(
            PdfConversionRun.tenant_id == tenant_id, PdfConversionRun.input_file_id == input_file_id
        )
        .order_by(PdfConversionRun.created_at.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()
