from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.search.service import SearchFilters, SearchService

router = APIRouter()

_ALLOWED_TYPES = {"documents", "people", "sites", "incidents", "inspections"}


@router.get("/search")
async def global_search(
    q: str = Query(min_length=1),
    types: str = "documents,people,sites,incidents,inspections",
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    status: str | None = None,
    company_id: str | None = None,
    site_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    requested_types = {item.strip() for item in types.split(",") if item.strip()}
    requested_types &= _ALLOWED_TYPES

    filters = SearchFilters(
        status=status,
        company_id=company_id,
        site_id=site_id,
        date_from=date_from,
        date_to=date_to,
    )
    service = SearchService(session=session, tenant_id=str(tenant.id))
    return await service.search(q=q, types=requested_types, filters=filters, limit=limit, cursor=cursor)
