from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, abac
from app.domains.incidents import append_log_entry, register_incident, update_incident
from app.models.models import (
    Incident,
    IncidentLog,
    IncidentPersonRole,
    IncidentStage,
    IncidentStatus,
    IncidentType,
    Tenant,
)
from app.schemas.incidents import (
    IncidentCreate,
    IncidentLogCreate,
    IncidentLogRead,
    IncidentPage,
    IncidentRead,
    IncidentUpdate,
)

router = APIRouter(tags=["incidents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_manager_roles = ["admin"]


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_manager_roles, action="read incidents")),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(abac(_tenant_resource_id, required_roles=_manager_roles, action="manage incidents")),
]


async def _get_incident(session: AsyncSession, tenant: Tenant, incident_id: str) -> Incident:
    stmt = (
        select(Incident)
        .options(selectinload(Incident.participants))
        .where(Incident.id == incident_id, Incident.tenant_id == tenant.id, Incident.deleted_at.is_(None))
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Incident not found")
    return record


def _serialize_incident(instance: Incident, victim_ids: list[str] | None = None) -> IncidentRead:
    computed = victim_ids
    if computed is None:
        participants = getattr(instance, "__dict__", {}).get("participants") or []
        computed = [
            str(link.person_id)
            for link in participants
            if getattr(link, "role", None) == IncidentPersonRole.VICTIM
        ]
    payload = IncidentRead.model_validate(instance)
    payload.victim_ids = list(computed)
    return payload


@router.get("/incidents", response_model=IncidentPage)
async def list_incidents(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    site_id: str | None = Query(default=None, min_length=1, max_length=36),
    status_filter: IncidentStatus | None = Query(default=None),
    incident_type: IncidentType | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> IncidentPage:
    stmt = select(Incident).options(selectinload(Incident.participants)).where(
        Incident.tenant_id == tenant.id, Incident.deleted_at.is_(None)
    )
    if company_id:
        stmt = stmt.where(Incident.company_id == company_id)
    if site_id:
        stmt = stmt.where(Incident.site_id == site_id)
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter)
    if incident_type:
        stmt = stmt.where(Incident.incident_type == incident_type)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Incident.occurred_at.desc()).offset(offset).limit(limit)
    items = (await session.execute(stmt)).scalars().unique().all()
    total = await session.scalar(total_stmt)
    return IncidentPage(items=[_serialize_incident(item) for item in items], total=int(total or 0))


@router.post("/incidents", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> IncidentRead:
    try:
        incident = await register_incident(
            session,
            tenant_id=str(tenant.id),
            title=payload.title,
            company_id=payload.company_id,
            site_id=payload.site_id,
            occurred_at=payload.occurred_at,
            incident_type=payload.incident_type,
            severity=payload.severity,
            description=payload.description,
            location_description=payload.location_description,
            pack_id=payload.pack_id,
            victim_ids=payload.victim_ids,
        )
    except ValueError as exc:  # pragma: no cover - defensive conversion to HTTP error
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    return _serialize_incident(incident, victim_ids=payload.victim_ids)


@router.get("/incidents/{incident_id}", response_model=IncidentRead)
async def get_incident(
    incident_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> IncidentRead:
    incident = await _get_incident(session, tenant, incident_id)
    return _serialize_incident(incident)


@router.patch("/incidents/{incident_id}", response_model=IncidentRead)
async def patch_incident(
    incident_id: str,
    payload: IncidentUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> IncidentRead:
    incident = await _get_incident(session, tenant, incident_id)
    updates = payload.model_dump(exclude_unset=True)
    victim_ids = updates.pop("victim_ids", None)
    try:
        updated = await update_incident(
            session,
            tenant_id=str(tenant.id),
            incident=incident,
            updates=updates,
            victim_ids=victim_ids,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return _serialize_incident(updated, victim_ids=victim_ids)


@router.post("/incidents/{incident_id}/logs", response_model=IncidentLogRead, status_code=status.HTTP_201_CREATED)
async def add_incident_log(
    incident_id: str,
    payload: IncidentLogCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> IncidentLogRead:
    incident = await _get_incident(session, tenant, incident_id)
    try:
        log_entry = await append_log_entry(
            session,
            tenant_id=str(tenant.id),
            incident=incident,
            message=payload.message,
            stage=payload.stage,
            status=payload.status,
            metadata=payload.metadata_json,
        )
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return IncidentLogRead.model_validate(log_entry)


@router.get("/incidents/{incident_id}/logs", response_model=list[IncidentLogRead])
async def list_incident_logs(
    incident_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> list[IncidentLogRead]:
    incident = await _get_incident(session, tenant, incident_id)
    stmt = (
        select(IncidentLog)
        .where(IncidentLog.incident_id == incident.id, IncidentLog.tenant_id == tenant.id)
        .order_by(IncidentLog.created_at.asc())
    )
    records = list((await session.execute(stmt)).scalars().all())
    return [IncidentLogRead.model_validate(record) for record in records]
