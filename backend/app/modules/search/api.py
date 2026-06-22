from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import MissingGreenlet, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import Tenant
from app.modules.projections.models import SearchIndexEntry
from app.modules.projections.services import ProjectionOrchestrator
from app.modules.search.service import SearchFilters, SearchService

router = APIRouter()

_ALLOWED_TYPES = {
    "person",
    "people",
    "employee",
    "employees",
    "company",
    "contractor",
    "site",
    "sites",
    "workplace",
    "document",
    "documents",
    "template",
    "templates",
    "package",
    "packages",
    "risk_map",
    "risk",
    "risks",
    "ppe_issue",
    "ppe",
    "training_enrollment",
    "training",
    "certificate",
    "briefing_entry",
    "incident",
    "incidents",
    "inspection",
    "inspections",
    "prescription",
    "prescriptions",
    "file",
    "files",
    "report",
    "task",
    "tasks",
    "workflow_task",
    "workflow_tasks",
    "npa",
    "contract",
    "contracts",
    "order",
    "orders",
}


@router.get("/search")
async def global_search(
    q: str = Query(default=""),
    entity_types: str | None = Query(default=None),
    types: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    sort: str = Query(default="relevance", pattern="^(relevance|updated_at|date)$"),
    status: str | None = None,
    company_id: str | None = None,
    site_id: str | None = None,
    project_id: str | None = None,
    contractor_id: str | None = None,
    risk_level: str | None = None,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> dict:
    raw_types = entity_types or types or "person,package,document,file,incident,inspection,site"
    requested_types = {item.strip() for item in raw_types.split(",") if item.strip()}
    requested_types &= _ALLOWED_TYPES

    filters = SearchFilters(
        status=status,
        company_id=company_id,
        site_id=site_id,
        project_id=project_id,
        contractor_id=contractor_id,
        risk_level=risk_level,
        date_from=date_from,
        date_to=date_to,
    )
    service = SearchService(session=session, tenant_id=str(tenant.id))
    try:
        payload = await service.search(
            q=q, types=requested_types, filters=filters, sort=sort, limit=limit, cursor=cursor
        )
    except (OperationalError, MissingGreenlet):
        await session.rollback()
        payload = {
            "q": q,
            "total": 0,
            "facets": {
                "type_counts": {},
                "status_counts": {},
                "company_counts": {},
                "site_counts": {},
                "project_counts": {},
                "risk_level_counts": {},
            },
            "items": [],
            "next_cursor": None,
        }
    try:
        await service.track_recent_query(
            user_id=access.user.id, q=q, entity_types=requested_types, filters=filters
        )
        await session.commit()
    except (OperationalError, MissingGreenlet):
        await session.rollback()
    payload["correlation_id"] = str(uuid4())
    return payload


@router.get("/search/suggest")
async def search_suggest(
    q: str = Query(default=""),
    limit: int = Query(default=10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> dict:
    like = f"%{q}%"
    stmt = select(SearchIndexEntry).where(SearchIndexEntry.tenant_id == str(tenant.id))
    if q:
        stmt = stmt.where(SearchIndexEntry.title.ilike(like))
    rows = (
        (await session.execute(stmt.order_by(SearchIndexEntry.updated_at.desc()).limit(limit)))
        .scalars()
        .all()
    )
    return {
        "items": [
            {
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "title": r.title,
                "route": r.route,
            }
            for r in rows
        ]
    }


@router.post("/search/reindex")
async def reindex_all(
    session: AsyncSession = Depends(get_session), tenant: Tenant = Depends(get_tenant_record)
) -> dict:
    count = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_search_index()
    return {"status": "ok", "indexed": count}


@router.post("/search/reindex/{entity_type}")
async def reindex_by_entity(
    entity_type: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    if entity_type not in _ALLOWED_TYPES:
        return {"status": "skipped", "entity_type": entity_type}
    count = await ProjectionOrchestrator(session, str(tenant.id)).rebuild_search_index()
    return {"status": "ok", "indexed": count, "entity_type": entity_type}


@router.get("/search/recent")
async def list_recent_searches(
    limit: int = Query(default=8, ge=1, le=20),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> dict:
    try:
        items = await SearchService(session=session, tenant_id=str(tenant.id)).list_recent_queries(
            user_id=access.user.id, limit=limit
        )
    except (OperationalError, MissingGreenlet):
        await session.rollback()
        items = []
    return {"items": items}


@router.get("/search/saved")
async def list_saved_searches(
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> dict:
    try:
        items = await SearchService(session=session, tenant_id=str(tenant.id)).list_saved_queries(
            user_id=access.user.id
        )
    except (OperationalError, MissingGreenlet):
        await session.rollback()
        items = []
    return {"items": items}


@router.post("/search/saved", status_code=status.HTTP_201_CREATED)
async def create_saved_search(
    payload: dict,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> dict:
    q = str(payload.get("q") or "").strip()
    name = str(payload.get("name") or q or "Saved search").strip()
    entity_types = {str(item).strip() for item in (payload.get("types") or []) if str(item).strip()}
    item = await SearchService(session=session, tenant_id=str(tenant.id)).save_query(
        user_id=access.user.id,
        name=name,
        q=q,
        entity_types=entity_types,
        filters=dict(payload.get("filters") or {}),
        is_shared=bool(payload.get("is_shared") or False),
    )
    await session.commit()
    return {
        "id": item.id,
        "name": item.name,
        "q": item.query_text,
        "types": item.entity_types or [],
        "filters": item.filters_json or {},
        "is_shared": item.is_shared,
    }


@router.delete("/search/saved/{saved_query_id}")
async def delete_saved_search(
    saved_query_id: str,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac()),
) -> dict:
    deleted = await SearchService(session=session, tenant_id=str(tenant.id)).delete_saved_query(
        user_id=access.user.id, saved_query_id=saved_query_id
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="saved search not found")
    await session.commit()
    return {"deleted": True}
