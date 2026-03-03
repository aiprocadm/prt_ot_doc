from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.models.models import Tenant
from app.modules.files.models import FileContentIndex, FileLink, FileRecord
from app.modules.search.service import SearchFilters, SearchService

router = APIRouter()

_ALLOWED_TYPES = {"documents", "people", "sites", "incidents", "inspections", "files", "ppe", "risk", "training", "jobs", "templates"}


@router.get("/search")
async def global_search(
    q: str = Query(default=""),
    types: str = "documents,people,sites,incidents,inspections,ppe,risk,training,files",
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    sort: str = Query(default="relevance", pattern="^(relevance|updated_at|date)$"),
    status: str | None = None,
    company_id: str | None = None,
    site_id: str | None = None,
    project_id: str | None = None,
    contractor_id: str | None = None,
    risk_level: str | None = None,
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
        project_id=project_id,
        contractor_id=contractor_id,
        risk_level=risk_level,
        date_from=date_from,
        date_to=date_to,
    )
    service = SearchService(session=session, tenant_id=str(tenant.id))
    payload = await service.search(q=q, types=requested_types, filters=filters, sort=sort, limit=limit, cursor=cursor)
    payload["correlation_id"] = str(uuid4())
    return payload


@router.get("/archive/files")
async def archive_files(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = None,
    status: str | None = None,
    site_id: str | None = None,
    project_id: str | None = None,
    contractor_id: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    sort: str = Query(default="updated_at", pattern="^(updated_at|date)$"),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    offset = int(cursor or "0") if (cursor or "0").isdigit() else 0
    stmt = select(FileRecord).where(FileRecord.tenant_id == str(tenant.id), FileRecord.deleted_at.is_(None))
    if status:
        stmt = stmt.where(FileRecord.status == status)
    if site_id:
        stmt = stmt.where(FileRecord.metadata_json["site_id"].astext == site_id)
    if project_id:
        stmt = stmt.where(FileRecord.metadata_json["project_id"].astext == project_id)
    if contractor_id:
        stmt = stmt.where(FileRecord.metadata_json["contractor_id"].astext == contractor_id)
    if date_from:
        stmt = stmt.where(FileRecord.updated_at >= datetime.combine(date_from, time.min))
    if date_to:
        stmt = stmt.where(FileRecord.updated_at <= datetime.combine(date_to, time.max))

    order_expr = FileRecord.updated_at.desc() if sort in {"updated_at", "date"} else FileRecord.updated_at.desc()
    stmt = stmt.order_by(order_expr).offset(offset).limit(limit + 1)
    records = (await session.execute(stmt)).scalars().all()

    file_ids = [record.id for record in records[:limit]]
    links_by_file: dict[str, list[dict[str, str]]] = {}
    if file_ids:
        links = (
            await session.execute(
                select(FileLink).where(FileLink.tenant_id == str(tenant.id), FileLink.file_id.in_(file_ids))
            )
        ).scalars().all()
        for link in links:
            links_by_file.setdefault(link.file_id, []).append({"entity_type": link.entity_type, "entity_id": link.entity_id, "role": link.role})

    has_more = len(records) > limit
    items = [
        {
            "id": record.id,
            "filename": record.original_filename or Path(record.object_key).name,
            "content_type": record.content_type,
            "size_bytes": record.size_bytes,
            "status": record.status,
            "updated_at": record.updated_at,
            "meta": (record.tags or record.metadata_json or {}),
            "links": links_by_file.get(record.id, []),
        }
        for record in records[:limit]
    ]
    return {"items": items, "next_cursor": str(offset + limit) if has_more else None, "correlation_id": str(uuid4())}


@router.get("/search/files")
async def search_files(
    q: str = Query(default=""),
    limit: int = Query(default=50, ge=1, le=200),
    status: str | None = None,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> dict:
    stmt = (
        select(FileRecord, FileContentIndex)
        .outerjoin(FileContentIndex, FileContentIndex.file_id == FileRecord.id)
        .where(FileRecord.tenant_id == str(tenant.id), FileRecord.deleted_at.is_(None))
    )
    if status:
        stmt = stmt.where(FileRecord.status == status)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            or_(
                FileRecord.object_key.ilike(like),
                FileRecord.original_filename.ilike(like),
                FileRecord.metadata_json.astext.ilike(like),
                FileContentIndex.raw_text.ilike(like),
            )
        )
    rows = (await session.execute(stmt.order_by(FileRecord.updated_at.desc()).limit(limit))).all()
    return {
        "items": [
            {
                "id": r.id,
                "filename": (r.original_filename or Path(r.object_key).name),
                "status": r.status,
                "updated_at": r.updated_at,
                "content_index_status": idx.status if idx else None,
            }
            for r, idx in rows
        ]
    }
