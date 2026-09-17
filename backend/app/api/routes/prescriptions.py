"""Prescription endpoints for inspection follow-ups."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.screen_access import screen_roles
from app.core.security import AccessContext, abac
from app.core.tenant_validation import TenantContextValidator
from app.db.session import rearm_session_tenant_context
from app.domains.prescriptions.lifecycle import (
    VERIFY_ROLES,
    InvalidTransition,
    evidence_satisfied,
    is_overdue,
    is_terminal,
    requires_evidence,
    validate_transition,
)
from app.domains.prescriptions.service import (
    list_overdue,
    notify_overdue,
    status_summary,
)
from app.models.models import Incident, Inspection, Prescription, PrescriptionStatus, User
from app.models.tenanting import Tenant
from app.modules.files.models import (
    FileEntityType,
    FileLink,
    FileLinkRole,
    FileRecord,
    FileStatus,
)
from app.schemas.prescriptions import (
    EvidenceFileRef,
    PrescriptionCreate,
    PrescriptionPage,
    PrescriptionRead,
    PrescriptionSummary,
    PrescriptionTransition,
    PrescriptionUpdate,
)
from app.services.audit import AuditService

# A file is acceptable as evidence only once antivirus scanning has cleared it.
_EVIDENCE_OK_FILE_STATUSES = frozenset({FileStatus.clean.value, FileStatus.ready.value})
_EVIDENCE_ENTITY_TYPE = FileEntityType.prescription.value
_EVIDENCE_ROLE = FileLinkRole.evidence.value

router = APIRouter(tags=["prescriptions"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]

# Роли берутся из единой карты прав экрана (core/screen_access): пункт меню
# виден ровно тем, кого пускает ручка — иначе человек видит раздел и получает
# 403 (docs/audit/ACCESS_MENU_VS_API.md, сторож tests/test_menu_matches_api.py).
_PRESCRIPTION_READ_ROLES = list(screen_roles("inspection.view"))
_PRESCRIPTION_WRITE_ROLES = ["admin", "owner", "hr", "line_manager"]


def _error_detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _to_read(record: Prescription, *, today: date) -> PrescriptionRead:
    """Serialize a prescription with a today-relative is_overdue flag."""
    return PrescriptionRead.model_validate(record).model_copy(
        update={"is_overdue": is_overdue(record.due_at, record.status, today)}
    )


async def _list_evidence_files(
    session: AsyncSession, *, tenant_id: str, prescription_id: str
) -> list[EvidenceFileRef]:
    """Evidence files linked to a prescription (FileLink role="evidence")."""
    rows = (
        await session.execute(
            select(FileLink, FileRecord)
            .join(FileRecord, FileRecord.id == FileLink.file_id)
            .where(
                FileLink.tenant_id == tenant_id,
                FileLink.entity_type == _EVIDENCE_ENTITY_TYPE,
                FileLink.entity_id == prescription_id,
                FileLink.role == _EVIDENCE_ROLE,
            )
        )
    ).all()
    return [
        EvidenceFileRef(
            file_id=file_rec.id,
            role=link.role,
            status=file_rec.status,
            display_name=file_rec.original_filename or Path(file_rec.object_key).name,
            size=file_rec.size_bytes,
        )
        for link, file_rec in rows
    ]


async def _to_read_with_files(
    session: AsyncSession, record: Prescription, *, tenant_id: str, today: date
) -> PrescriptionRead:
    """``_to_read`` plus the prescription's linked evidence files."""
    files = await _list_evidence_files(session, tenant_id=tenant_id, prescription_id=record.id)
    return _to_read(record, today=today).model_copy(update={"evidence_files": files})


async def _collect_evidence_files(
    session: AsyncSession, *, tenant_id: str, file_ids: list[str]
) -> list[FileRecord]:
    """Resolve evidence file ids, enforcing tenant ownership and clean AV status.

    Raises 404 ``evidence_file_not_found`` for unknown/cross-tenant/deleted files
    and 422 ``evidence_file_not_clean`` for files not yet cleared by antivirus.
    """
    records: list[FileRecord] = []
    for file_id in file_ids:
        record = await session.get(FileRecord, file_id)
        if record is None or record.tenant_id != tenant_id or record.deleted_at is not None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail=_error_detail("evidence_file_not_found", "Evidence file not found"),
            )
        if record.status not in _EVIDENCE_OK_FILE_STATUSES:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=_error_detail(
                    "evidence_file_not_clean",
                    "Evidence file is not antivirus-clean",
                ),
            )
        records.append(record)
    return records


async def _link_evidence_files(
    session: AsyncSession, *, tenant_id: str, prescription_id: str, records: list[FileRecord]
) -> None:
    """Attach validated files to a prescription via FileLink (idempotent)."""
    for record in records:
        already_linked = (
            await session.execute(
                select(FileLink.id).where(
                    FileLink.tenant_id == tenant_id,
                    FileLink.file_id == record.id,
                    FileLink.entity_type == _EVIDENCE_ENTITY_TYPE,
                    FileLink.entity_id == prescription_id,
                    FileLink.role == _EVIDENCE_ROLE,
                )
            )
        ).scalar_one_or_none()
        if already_linked is not None:
            continue
        session.add(
            FileLink(
                tenant_id=tenant_id,
                file_id=record.id,
                entity_type=_EVIDENCE_ENTITY_TYPE,
                entity_id=prescription_id,
                role=_EVIDENCE_ROLE,
            )
        )


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> str | None:
    return getattr(tenant, "id", None)


ManagerAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_PRESCRIPTION_READ_ROLES,
            action="read prescriptions",
        )
    ),
]
EditorAccess = Annotated[
    AccessContext,
    Depends(
        abac(
            _tenant_resource_id,
            required_roles=_PRESCRIPTION_WRITE_ROLES,
            action="manage prescriptions",
        )
    ),
]


async def _get_inspection(session: AsyncSession, tenant_id: str, inspection_id: str) -> Inspection:
    stmt = select(Inspection).where(
        Inspection.id == inspection_id,
        Inspection.tenant_id == tenant_id,
        Inspection.deleted_at.is_(None),
    )
    inspection = (await session.execute(stmt)).scalar_one_or_none()
    if inspection is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("inspection_not_found", "Inspection not found"),
        )
    return inspection


async def _get_incident(session: AsyncSession, tenant_id: str, incident_id: str) -> Incident:
    stmt = select(Incident).where(
        Incident.id == incident_id,
        Incident.tenant_id == tenant_id,
        Incident.deleted_at.is_(None),
    )
    incident = (await session.execute(stmt)).scalar_one_or_none()
    if incident is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("incident_not_found", "Incident not found"),
        )
    return incident


async def _get_user(session: AsyncSession, tenant_id: str, user_id: str) -> User:
    stmt = select(User).where(
        User.id == user_id, User.tenant_id == tenant_id, User.deleted_at.is_(None)
    )
    user = (await session.execute(stmt)).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("user_not_found", "User not found"),
        )
    return user


async def _get_prescription(
    session: AsyncSession, tenant_id: str, prescription_id: str
) -> Prescription:
    stmt = select(Prescription).where(
        Prescription.id == prescription_id,
        Prescription.tenant_id == tenant_id,
        Prescription.deleted_at.is_(None),
    )
    record = (await session.execute(stmt)).scalar_one_or_none()
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=_error_detail("prescription_not_found", "Prescription not found"),
        )
    return record


@router.get("/prescriptions", response_model=PrescriptionPage)
async def list_prescriptions(
    request: Request,
    response: Response,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
    inspection_id: str | None = Query(default=None, min_length=1, max_length=36),
    incident_id: str | None = Query(default=None, min_length=1, max_length=36),
    status_filter: PrescriptionStatus | None = Query(default=None, alias="status"),
    assignee_id: str | None = Query(default=None, min_length=1, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> PrescriptionPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()

    stmt = select(Prescription).where(
        Prescription.tenant_id == tenant.id, Prescription.deleted_at.is_(None)
    )
    if inspection_id:
        stmt = stmt.where(Prescription.inspection_id == inspection_id)
    if incident_id:
        stmt = stmt.where(Prescription.incident_id == incident_id)
    if status_filter:
        stmt = stmt.where(Prescription.status == status_filter)
    if assignee_id:
        stmt = stmt.where(Prescription.assignee_id == assignee_id)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    stmt = stmt.order_by(Prescription.due_at.desc().nullslast(), Prescription.created_at.desc())
    stmt = stmt.offset(offset).limit(limit)
    items = list((await session.execute(stmt)).scalars().all())
    total = await session.scalar(total_stmt)
    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=items,
        scalars=[
            ("total", int(total or 0)),
            ("limit", limit),
            ("offset", offset),
            ("inspection", inspection_id or ""),
            ("incident", incident_id or ""),
            ("status", status_filter.value if status_filter else ""),
            ("assignee", assignee_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return PrescriptionPage(
        items=[_to_read(item, today=today) for item in items],
        total=int(total or 0),
    )


@router.post("/prescriptions", response_model=PrescriptionRead, status_code=status.HTTP_201_CREATED)
async def create_prescription(
    request: Request,
    payload: PrescriptionCreate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    await _get_inspection(session, str(tenant.id), payload.inspection_id)
    if payload.incident_id:
        await _get_incident(session, str(tenant.id), payload.incident_id)
    if payload.assignee_id:
        await _get_user(session, str(tenant.id), payload.assignee_id)

    record = Prescription(
        tenant_id=str(tenant.id),
        inspection_id=payload.inspection_id,
        incident_id=payload.incident_id,
        description=payload.description,
        due_at=payload.due_at,
        assignee_id=payload.assignee_id,
    )
    session.add(record)
    await session.flush()
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="create",
        object_type="prescription",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"inspection_id": record.inspection_id},
    )
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return _to_read(record, today=datetime.now(timezone.utc).date())


@router.get("/prescriptions/overdue", response_model=PrescriptionPage)
async def list_overdue_prescriptions(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> PrescriptionPage:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    items = await list_overdue(session, tenant_id=str(tenant.id), today=today)
    return PrescriptionPage(
        items=[_to_read(item, today=today) for item in items],
        total=len(items),
    )


@router.get("/prescriptions/summary", response_model=PrescriptionSummary)
async def prescriptions_summary(
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> PrescriptionSummary:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    data = await status_summary(session, tenant_id=str(tenant.id), today=today)
    return PrescriptionSummary(**data)


@router.post("/prescriptions/remind-overdue")
async def remind_overdue_prescriptions(
    request: Request,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> dict[str, object]:
    TenantContextValidator.ensure_tenant_context(tenant)
    today = datetime.now(timezone.utc).date()
    actor_id = getattr(access.user, "id", None)
    overdue = await notify_overdue(
        session, tenant_id=str(tenant.id), actor_id=actor_id, today=today
    )
    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="notify_overdue",
        object_type="prescription",
        object_id="bulk",
        user_id=actor_id,
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"count": len(overdue)},
    )
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    return {
        "count": len(overdue),
        "items": [_to_read(p, today=today) for p in overdue],
    }


@router.get("/prescriptions/{prescription_id}", response_model=PrescriptionRead)
async def get_prescription(
    prescription_id: str,
    tenant: TenantDep,
    session: SessionDep,
    _: ManagerAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await _get_prescription(session, str(tenant.id), prescription_id)
    return await _to_read_with_files(
        session, record, tenant_id=str(tenant.id), today=datetime.now(timezone.utc).date()
    )


@router.patch("/prescriptions/{prescription_id}", response_model=PrescriptionRead)
async def update_prescription(
    request: Request,
    prescription_id: str,
    payload: PrescriptionUpdate,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await _get_prescription(session, str(tenant.id), prescription_id)
    updates = payload.model_dump(exclude_unset=True)
    if "inspection_id" in updates and updates["inspection_id"]:
        await _get_inspection(session, str(tenant.id), str(updates["inspection_id"]))
    if "incident_id" in updates and updates["incident_id"]:
        await _get_incident(session, str(tenant.id), str(updates["incident_id"]))
    if "assignee_id" in updates and updates["assignee_id"]:
        await _get_user(session, str(tenant.id), str(updates["assignee_id"]))

    for key, value in updates.items():
        setattr(record, key, value)

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="update",
        object_type="prescription",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={"status": record.status.value},
    )
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return _to_read(record, today=datetime.now(timezone.utc).date())


@router.post("/prescriptions/{prescription_id}/transition", response_model=PrescriptionRead)
async def transition_prescription(
    request: Request,
    prescription_id: str,
    payload: PrescriptionTransition,
    tenant: TenantDep,
    session: SessionDep,
    access: EditorAccess,
) -> PrescriptionRead:
    TenantContextValidator.ensure_tenant_context(tenant)

    record = await _get_prescription(session, str(tenant.id), prescription_id)
    current = record.status
    target = payload.to

    try:
        validate_transition(current, target)
    except InvalidTransition as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=_error_detail("prescription_invalid_transition", str(exc)),
        )

    # Idempotent no-op: same state, no write, no audit row.
    if current == target:
        return await _to_read_with_files(
            session, record, tenant_id=str(tenant.id), today=datetime.now(timezone.utc).date()
        )

    # Segregation of duties: only admin/owner may verify (повторная проверка).
    if target == PrescriptionStatus.VERIFIED:
        roles = {value.lower() for value in access.to_auth_context().roles}
        if not roles & VERIFY_ROLES:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail=_error_detail(
                    "prescription_verify_forbidden",
                    "Only admin or owner may verify prescriptions",
                ),
            )

    # Validate any newly-supplied evidence files up front (tenant-owned + clean).
    new_evidence_files = await _collect_evidence_files(
        session, tenant_id=str(tenant.id), file_ids=payload.evidence_file_ids or []
    )

    # Evidence is required to complete: a textual note OR at least one file
    # (newly supplied or already linked) satisfies it.
    effective_evidence = payload.evidence if payload.evidence is not None else record.evidence
    has_text = bool(effective_evidence and effective_evidence.strip())
    existing_file_count = len(
        await _list_evidence_files(session, tenant_id=str(tenant.id), prescription_id=record.id)
    )
    total_file_count = existing_file_count + len(new_evidence_files)
    if requires_evidence(target) and not evidence_satisfied(
        has_text=has_text, file_count=total_file_count
    ):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=_error_detail(
                "evidence_required", "Evidence is required to complete a prescription"
            ),
        )

    record.status = target
    if payload.evidence is not None:
        record.evidence = payload.evidence
    await _link_evidence_files(
        session, tenant_id=str(tenant.id), prescription_id=record.id, records=new_evidence_files
    )
    if is_terminal(target):
        record.closed_at = datetime.now(timezone.utc)

    audit = AuditService(session)
    ip = request.client.host if request.client else "unknown"
    await audit.log_event(
        tenant_id=str(tenant.id),
        action="transition",
        object_type="prescription",
        object_id=record.id,
        user_id=getattr(access.user, "id", None),
        ip=ip,
        request_id=getattr(request.state, "trace_id", None),
        user_agent=request.headers.get("user-agent"),
        details={
            "from": current.value,
            "to": target.value,
            "evidence_present": bool(record.evidence),
            "evidence_files_added": len(new_evidence_files),
            "note": payload.note,
        },
    )
    await session.commit()
    # commit() drops the transaction-local RLS GUCs — re-arm before
    # further session work (SEC-65)
    await rearm_session_tenant_context(session)
    await session.refresh(record)
    return await _to_read_with_files(
        session, record, tenant_id=str(tenant.id), today=datetime.now(timezone.utc).date()
    )
