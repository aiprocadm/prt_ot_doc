from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.disciplines import DISCIPLINE_TITLES, Discipline
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import (
    Incident,
    IncidentLog,
    IncidentPersonRole,
    IncidentStatus,
    IncidentType,
    Tenant,
)
from app.modules.incidents import append_log_entry, register_incident, update_incident
from app.schemas.incidents import (
    IncidentCreate,
    IncidentLogCreate,
    IncidentLogRead,
    IncidentPage,
    IncidentRead,
    IncidentUpdate,
)
from app.services.audit import AuditService
from app.services.outbox import OutboxService

router = APIRouter(tags=["incidents"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

_INCIDENT_READ_ROLES = ["admin"]
_INCIDENT_WRITE_ROLES = ["admin"]

#: дисциплина происшествия — код из ОБЩЕГО словаря (in01, разд. 54.2); тот же
#: приём, что у курса обучения и стажировки
_DISCIPLINE_CODES = {d.value: DISCIPLINE_TITLES[d] for d in Discipline}


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_INCIDENT_READ_ROLES, action="read incidents")
    ),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(
        abac(_tenant_resource_id, required_roles=_INCIDENT_WRITE_ROLES, action="manage incidents")
    ),
]


def _incident_bad_request(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=api_problem_detail(
            code="INCIDENT_VALIDATION_ERROR", message=message, error_type="incidents"
        ),
    )


def _validate_discipline(discipline: str | None) -> None:
    """Неизвестный код — ошибка запроса, а не тихая запись «чего-то»."""

    if discipline is not None and discipline not in _DISCIPLINE_CODES:
        raise _incident_bad_request(
            f"Неизвестная дисциплина {discipline!r}; допустимые: {', '.join(_DISCIPLINE_CODES)}"
        )


async def _get_incident(session: AsyncSession, tenant: Tenant, incident_id: str) -> Incident:
    stmt = (
        select(Incident)
        .options(selectinload(Incident.participants))
        .where(
            Incident.id == incident_id,
            Incident.tenant_id == tenant.id,
            Incident.deleted_at.is_(None),
        )
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
    # Подпись дисциплины — словами из общего словаря; пусто, если не размечена
    payload.discipline_label = (
        _DISCIPLINE_CODES.get(instance.discipline) if instance.discipline else None
    )
    return payload


@router.get("/incidents", response_model=IncidentPage)
async def list_incidents(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    company_id: str | None = Query(default=None, min_length=1, max_length=36),
    site_id: str | None = Query(default=None, min_length=1, max_length=36),
    status_filter: IncidentStatus | None = Query(default=None),
    incident_type: IncidentType | None = Query(default=None),
    discipline: str | None = Query(default=None, max_length=32),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> IncidentPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_discipline(discipline)

    stmt = (
        select(Incident)
        .options(selectinload(Incident.participants))
        .where(Incident.tenant_id == tenant.id, Incident.deleted_at.is_(None))
    )
    if company_id:
        stmt = stmt.where(Incident.company_id == company_id)
    if site_id:
        stmt = stmt.where(Incident.site_id == site_id)
    if status_filter:
        stmt = stmt.where(Incident.status == status_filter)
    if incident_type:
        stmt = stmt.where(Incident.incident_type == incident_type)
    if discipline:
        stmt = stmt.where(Incident.discipline == discipline)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Incident.occurred_at.desc()).offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().unique().all())
    total = await session.scalar(total_stmt)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("company", company_id or ""),
            ("site", site_id or ""),
            ("status", status_filter.value if status_filter else ""),
            ("type", incident_type.value if incident_type else ""),
            ("discipline", discipline or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return IncidentPage(items=[_serialize_incident(item) for item in items], total=int(total or 0))


@router.post("/incidents", response_model=IncidentRead, status_code=status.HTTP_201_CREATED)
async def create_incident(
    request: Request,
    payload: IncidentCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> IncidentRead:
    TenantContextValidator.ensure_tenant_context(tenant)
    _validate_discipline(payload.discipline)

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
            discipline=payload.discipline,
        )
    except ValueError as exc:  # pragma: no cover - defensive conversion to HTTP error
        raise _incident_bad_request(str(exc)) from exc

    await AuditService(session).log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="incident",
        object_id=incident.id,
        user_id=getattr(access.user, "id", None),
        ip=request.client.host if request.client else "unknown",
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"status": incident.status.value, "severity": incident.severity.value},
    )
    await OutboxService(session).enqueue(
        tenant_id=str(tenant.id),
        event_type="IncidentCreated",
        payload={
            "tenant_id": str(tenant.id),
            "incident_id": incident.id,
            "company_id": incident.company_id,
            "site_id": incident.site_id,
            "status": incident.status.value,
            "severity": incident.severity.value,
            "incident_type": incident.incident_type.value,
            "actor_id": getattr(access.user, "id", None),
        },
    )
    await session.commit()

    return _serialize_incident(incident, victim_ids=payload.victim_ids)


@router.get("/incidents/{incident_id}", response_model=IncidentRead)
async def get_incident(
    incident_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> IncidentRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    incident = await _get_incident(session, tenant, incident_id)
    return _serialize_incident(incident)


@router.patch("/incidents/{incident_id}", response_model=IncidentRead)
@audit_operation("update", "incident")
async def patch_incident(
    incident_id: str,
    payload: IncidentUpdate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> IncidentRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    incident = await _get_incident(session, tenant, incident_id)
    updates = payload.model_dump(exclude_unset=True)
    if "discipline" in updates:
        _validate_discipline(updates["discipline"])
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
        raise _incident_bad_request(str(exc)) from exc
    return _serialize_incident(updated, victim_ids=victim_ids)


@router.post(
    "/incidents/{incident_id}/logs",
    response_model=IncidentLogRead,
    status_code=status.HTTP_201_CREATED,
)
@audit_operation("create_log", "incident_log")
async def add_incident_log(
    incident_id: str,
    payload: IncidentLogCreate,
    tenant: TenantDep,
    session: SessionDep,
    _: EditorAccess,
) -> IncidentLogRead:
    TenantContextValidator.ensure_tenant_context(tenant)

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
        raise _incident_bad_request(str(exc)) from exc
    return IncidentLogRead.model_validate(log_entry)


@router.get("/incidents/{incident_id}/logs", response_model=list[IncidentLogRead])
async def list_incident_logs(
    incident_id: str,
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> list[IncidentLogRead] | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    incident = await _get_incident(session, tenant, incident_id)
    stmt = (
        select(IncidentLog)
        .where(IncidentLog.incident_id == incident.id, IncidentLog.tenant_id == tenant.id)
        .order_by(IncidentLog.created_at.asc())
    )
    records = list((await session.execute(stmt)).scalars().all())
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=records,
        scalars=[("incident", str(incident.id))],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return [IncidentLogRead.model_validate(record) for record in records]
