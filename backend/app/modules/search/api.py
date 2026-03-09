from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.projections.models import SearchIndexEntry
from app.modules.projections.services import ProjectionOrchestrator
from app.modules.search.service import SearchFilters, SearchService

router = APIRouter()

_ALLOWED_TYPES = {
    "person",
    "company",
    "contractor",
    "site",
    "workplace",
    "document",
    "template",
    "package",
    "risk_map",
    "ppe_issue",
    "training_enrollment",
    "certificate",
    "briefing_entry",
    "incident",
    "inspection",
    "prescription",
    "file",
    "report",
}


@router.get("/search")
async def global_search(
    q: str = Query(default=""),
    entity_types: str = Query(default="person,package,document,file,incident,inspection,site"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    sort: str = Query(default="relevance", pattern="^(relevance|updated_at|date)$"),
    status: str | None = None,
    company_id: str | None = None,
    site_id: str | None = None,
    project_id: str | None = None,
    contractor_id: str | None = None,
    risk_level: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    requested_types = {item.strip() for item in entity_types.split(",") if item.strip()}
    requested_types &= _ALLOWED_TYPES

    filters = SearchFilters(
        status=status,
        company_id=company_id,
        site_id=site_id,
        project_id=project_id,
        contractor_id=contractor_id,
        risk_level=risk_level,
    )
    service = SearchService(session=session, tenant_id=str(tenant.id))
    payload = await service.search(q=q, types=requested_types, filters=filters, sort=sort, limit=limit, cursor=cursor)
    payload["correlation_id"] = str(uuid4())
    return payload


@router.get("/search/suggest")
async def search_suggest(
    q: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    like = f"%{q}%"
    stmt = select(SearchIndexEntry).where(SearchIndexEntry.tenant_id == str(tenant.id))
    if q:
        stmt = stmt.where(SearchIndexEntry.title.ilike(like))
    rows = (await session.execute(stmt.order_by(SearchIndexEntry.updated_at.desc()).limit(limit))).scalars().all()
    return {"items": [{"entity_type": r.entity_type, "entity_id": r.entity_id, "title": r.title, "route": r.route} for r in rows]}


@router.post("/search/reindex")
async def reindex_all(session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict:
    count = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_search_index()
    return {"status": "ok", "indexed": count}


@router.post("/search/reindex/{entity_type}")
async def reindex_by_entity(entity_type: str, session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)) -> dict:
    if entity_type not in _ALLOWED_TYPES:
        return {"status": "skipped", "entity_type": entity_type}
    count = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_search_index()
    return {"status": "ok", "indexed": count, "entity_type": entity_type}
