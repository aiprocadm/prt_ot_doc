from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Template, TemplateVersion


async def get_template_version_by_code(
    session: AsyncSession, *, tenant_id: str, code: str, version: int
) -> tuple[Template, TemplateVersion] | None:
    stmt = (
        select(Template, TemplateVersion)
        .join(TemplateVersion, TemplateVersion.template_id == Template.id)
        .where(
            Template.tenant_id == tenant_id,
            TemplateVersion.tenant_id == tenant_id,
            Template.code == code,
            TemplateVersion.version == version,
        )
        .limit(1)
    )
    row = (await session.execute(stmt)).first()
    if row is None:
        return None
    return row
