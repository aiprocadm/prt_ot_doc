from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant

router = APIRouter()


@router.get("/search")
async def global_search(
    q: str = Query(min_length=1),
    types: str = "files,documents",
    limit: int = 20,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    if "files" not in {item.strip() for item in types.split(",") if item.strip()}:
        return {"q": q, "items": []}
    stmt = text(
        """
        select fv.id as id, fv.filename as title, fti.excerpt as snippet
        from file_versions fv
        join file_objects fo on fo.id = fv.file_id
        left join file_text_index fti on fti.file_version_id = fv.id
        where fv.tenant_id = :tenant_id
          and fv.status = 'ready'
          and (fv.filename ilike :q or coalesce(fti.raw_text, '') ilike :q)
        order by fv.updated_at desc
        limit :limit offset :offset
        """
    )
    rows = (await session.execute(stmt, {"tenant_id": str(tenant.id), "q": f"%{q}%", "limit": limit, "offset": offset})).mappings().all()
    items = [{"type": "file", "id": row["id"], "title": row["title"], "snippet": row.get("snippet"), "score": 1.0, "meta": {}} for row in rows]
    return {"q": q, "items": items}
