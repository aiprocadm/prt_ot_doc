from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterable
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.rbac_abac import ROLE_PERMISSIONS
from app.core.security import AccessContext, rbac
from app.models.models import (
    BriefingJournal,
    BriefingTemplate,
    ComplianceDeadline,
    OfflineMediaQueue,
    OfflineSyncBatch,
    Person,
    Tenant,
    TrainingEnrollment,
)
from app.modules.pwa_sync.services import OfflineSyncService

router = APIRouter(prefix="/pwa", tags=["pwa"])
logger = logging.getLogger(__name__)

PWA_ROUTE_PERMISSION_MAP: dict[str, tuple[str, ...]] = {
    "dashboard": ("dashboard.read",),
    "briefings": ("briefings.read", "briefings.write"),
    "training": ("training.read", "training.write"),
    "tasks": ("tasks.read", "tasks.write"),
    "incidents": ("incidents.read", "incidents.write"),
    "inspections": ("inspections.read", "inspections.write"),
    "documents": ("documents.read", "documents.write"),
    "files": ("files.read", "files.write"),
}


class PwaCurrentUser(BaseModel):
    id: str
    email: str | None = None
    role: str
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    company_id: str | None = None
    tenant_id: str | None = None
    tenant_slug: str | None = None

    model_config = ConfigDict(extra="forbid")


class PwaTenantBranding(BaseModel):
    slug: str
    name: str

    model_config = ConfigDict(extra="forbid")


class PwaRoutePermission(BaseModel):
    route: str
    allowed: bool
    permissions: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class PwaBriefingTemplateProjection(BaseModel):
    id: str
    code: str
    title: str
    briefing_type: str
    status: str
    validity_days: int | None = None
    updated_at: datetime | None = None


class PwaBriefingJournalProjection(BaseModel):
    id: str
    code: str
    title: str
    journal_type: str
    status: str
    site_id: str | None = None
    department_id: str | None = None
    updated_at: datetime | None = None


class PwaTrainingEnrollmentProjection(BaseModel):
    id: str
    training_program_id: str
    training_group_id: str | None = None
    person_id: str | None = None
    status: str
    due_at: datetime | None = None
    expires_at: datetime | None = None
    progress_percent: float
    attempt_count: int
    updated_at: datetime | None = None


class PwaDeadlineProjection(BaseModel):
    id: str
    entity_type: str
    entity_id: str
    status: str
    person_id: str | None = None
    site_id: str | None = None
    due_at: datetime


class PwaConflictProjection(BaseModel):
    id: str
    entity_type: str
    device_id: str | None = None
    conflict_code: str
    status: str
    failed_at: datetime | None = None


class PwaBootstrapResponse(BaseModel):
    current_user: PwaCurrentUser
    tenant_branding: PwaTenantBranding
    route_permissions: list[PwaRoutePermission] = Field(default_factory=list)
    briefing_templates: list[PwaBriefingTemplateProjection] = Field(default_factory=list)
    active_journals: list[PwaBriefingJournalProjection] = Field(default_factory=list)
    assigned_training: list[PwaTrainingEnrollmentProjection] = Field(default_factory=list)
    compliance_deadlines_summary: dict[str, Any] = Field(default_factory=dict)
    offline_queue: dict[str, Any] = Field(default_factory=dict)
    dictionaries: dict[str, Any] = Field(default_factory=dict)
    sync_state: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


def _decimal_to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _normalize_permissions(access: AccessContext) -> list[str]:
    roles = access.to_auth_context().roles
    permissions = {
        permission.replace(":", ".")
        for role in roles
        for permission in ROLE_PERMISSIONS.get(role, set())
    }
    return sorted(permissions)


def _route_permissions(permission_codes: Iterable[str]) -> list[PwaRoutePermission]:
    granted = set(permission_codes)
    projections: list[PwaRoutePermission] = []
    for route_name, required_permissions in PWA_ROUTE_PERMISSION_MAP.items():
        matched = sorted(permission for permission in required_permissions if permission in granted)
        projections.append(
            PwaRoutePermission(
                route=route_name,
                allowed=bool(matched),
                permissions=matched,
            )
        )
    return projections


def _permissions_etag(permission_codes: Iterable[str]) -> str:
    serialized = "|".join(sorted(set(permission_codes)))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _build_conflict_resolution_contract(conflict_count: int) -> dict[str, Any]:
    return {
        "required": conflict_count > 0,
        "strategies": ["server_wins", "client_retry", "manual_review"],
        "recommended_action": "manual_review" if conflict_count > 0 else "continue_sync",
    }


def _build_draft_policy(*, pending_batches: int, failed_batches: int) -> dict[str, Any]:
    return {
        "local_persistence": True,
        "resume_supported": True,
        "retry_supported": True,
        "requires_review_before_retry": failed_batches > 0,
        "pending_draft_count": pending_batches,
    }


def _serialize_template(item: BriefingTemplate) -> PwaBriefingTemplateProjection:
    return PwaBriefingTemplateProjection(
        id=str(item.id),
        code=item.code,
        title=item.title,
        briefing_type=item.briefing_type,
        status=item.status,
        validity_days=item.validity_days,
        updated_at=item.updated_at,
    )


def _serialize_journal(item: BriefingJournal) -> PwaBriefingJournalProjection:
    return PwaBriefingJournalProjection(
        id=str(item.id),
        code=item.code,
        title=item.title,
        journal_type=item.journal_type,
        status=item.status,
        site_id=item.site_id,
        department_id=item.department_id,
        updated_at=item.updated_at,
    )


def _serialize_enrollment(item: TrainingEnrollment) -> PwaTrainingEnrollmentProjection:
    return PwaTrainingEnrollmentProjection(
        id=str(item.id),
        training_program_id=str(item.training_program_id),
        training_group_id=item.training_group_id,
        person_id=item.person_id,
        status=item.status,
        due_at=item.due_at,
        expires_at=item.expires_at,
        progress_percent=_decimal_to_float(item.progress_percent),
        attempt_count=int(item.attempt_count or 0),
        updated_at=item.updated_at,
    )


def _serialize_deadline(item: ComplianceDeadline) -> PwaDeadlineProjection:
    return PwaDeadlineProjection(
        id=str(item.id),
        entity_type=item.entity_type,
        entity_id=str(item.entity_id),
        status=item.status,
        person_id=item.person_id,
        site_id=item.site_id,
        due_at=item.due_at,
    )


def _build_dictionaries() -> dict[str, Any]:
    return {
        "briefing_types": ["introductory", "primary", "repeat", "target", "unscheduled"],
        "briefing_statuses": [
            "draft",
            "assigned",
            "signed_employee",
            "signed_instructor",
            "completed",
        ],
        "training_statuses": ["assigned", "in_progress", "completed", "failed"],
        "compliance_deadline_statuses": ["upcoming", "due", "overdue"],
        "offline_batch_statuses": ["pending", "applied", "failed"],
        "offline_media_statuses": ["pending", "uploaded", "failed"],
        "sync_conflict_codes": ["conflict_final_record"],
        "offline_capabilities": [
            "briefing_mark",
            "incident_draft",
            "checklist_draft",
            "task_comment_capture",
            "media_photo_sync",
            "training_acknowledgement",
        ],
    }


def _build_sync_state(
    *, pending_batches: int, failed_batches: int, pending_media: int, failed_media: int
) -> dict[str, Any]:
    return {
        "pending_batches": pending_batches,
        "failed_batches": failed_batches,
        "pending_media": pending_media,
        "failed_media": failed_media,
        "has_blocking_failures": failed_batches > 0 or failed_media > 0,
    }


def _build_offline_capabilities(permission_codes: Iterable[str]) -> dict[str, bool]:
    granted = set(permission_codes)
    return {
        "briefing_mark": bool({"briefings.read", "briefings.write"} & granted),
        "incident_draft": bool({"incidents.read", "incidents.write"} & granted),
        "checklist_draft": bool({"inspections.read", "inspections.write"} & granted),
        "task_comment_capture": bool({"tasks.read", "tasks.write"} & granted),
        "media_photo_sync": bool({"files.read", "files.write"} & granted),
        "training_acknowledgement": bool({"training.read", "training.write"} & granted),
    }


def _serialize_conflict(item: OfflineSyncBatch) -> PwaConflictProjection:
    payload = item.error_payload or {}
    return PwaConflictProjection(
        id=str(item.id),
        entity_type=item.entity_type,
        device_id=item.device_id,
        conflict_code=str(payload.get("error") or "unknown_conflict"),
        status=item.status,
        failed_at=item.updated_at,
    )


def _serialize_date(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return value.isoformat()


def _validate_payload_required_fields(
    payload: dict[str, Any], required_fields: tuple[str, ...]
) -> None:
    missing = [field for field in required_fields if payload.get(field) in (None, "")]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="PWA_SYNC_VALIDATION_ERROR",
                message=f"missing required fields: {', '.join(missing)}",
                error_type="pwa",
            ),
        )


def _sanitize_client_payload(
    payload: dict[str, Any], blocked_fields: tuple[str, ...]
) -> dict[str, Any]:
    sanitized = dict(payload)
    for field in blocked_fields:
        sanitized.pop(field, None)
    return sanitized


def _sanitize_offline_entity_payload(payload: Any) -> Any:
    blocked = {"tenant_id", "tenant_slug", "user_id", "company_id"}
    if isinstance(payload, dict):
        result: dict[str, Any] = {}
        for key, value in payload.items():
            if key in blocked:
                continue
            result[key] = _sanitize_offline_entity_payload(value)
        return result
    if isinstance(payload, list):
        return [_sanitize_offline_entity_payload(value) for value in payload]
    return payload


def _ensure_owner_or_admin(*, access: AccessContext, owner_user_id: str) -> None:
    roles = set(access.to_auth_context().roles)
    current_user_id = str(access.user.id)
    if owner_user_id != current_user_id and "admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=api_problem_detail(
                code="PWA_SYNC_FORBIDDEN",
                message="batch is not available for current user",
                error_type="pwa",
            ),
        )


@router.post("/sync/batch")
@audit_operation("sync_batch", "offline_sync_batch")
async def create_batch(
    payload: dict,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    access: AccessContext = Depends(rbac()),
):
    incoming = dict(payload or {})
    _validate_payload_required_fields(incoming, ("device_id", "entity_type", "payload"))
    sanitized = _sanitize_client_payload(
        incoming, ("tenant_id", "user_id", "status", "error_payload")
    )
    sanitized["payload"] = _sanitize_offline_entity_payload(sanitized.get("payload") or {})
    batch = OfflineSyncBatch(
        tenant_id=tenant.id,
        user_id=str(access.user.id),
        status="pending",
        **sanitized,
    )
    session.add(batch)
    await session.flush()
    updated = await OfflineSyncService().apply_batch(session, batch)
    logger.info(
        "pwa.sync.batch_processed",
        extra={
            "tenant_id": str(tenant.id),
            "user_id": str(access.user.id),
            "batch_id": str(updated.id),
            "entity_type": updated.entity_type,
            "status": updated.status,
            "conflict": updated.status == "failed",
        },
    )
    return updated


@router.get("/sync/status/{batch_id}")
async def sync_status(
    batch_id: str,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    access: AccessContext = Depends(rbac()),
):
    batch = await OfflineSyncService().get_status(session, batch_id, tenant_id=str(tenant.id))
    if not batch:
        raise HTTPException(404, "Batch not found")
    _ensure_owner_or_admin(access=access, owner_user_id=str(batch.user_id))
    return batch


@router.post("/media/commit")
@audit_operation("commit_media", "offline_media")
async def commit_media(
    payload: dict,
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    access: AccessContext = Depends(rbac()),
):
    incoming = dict(payload or {})
    _validate_payload_required_fields(incoming, ("device_id", "local_ref"))
    sanitized = _sanitize_client_payload(
        incoming, ("tenant_id", "user_id", "upload_status", "file_id")
    )
    media = OfflineMediaQueue(
        tenant_id=tenant.id,
        user_id=str(access.user.id),
        upload_status="pending",
        **sanitized,
    )
    session.add(media)
    await session.flush()
    updated = await OfflineSyncService().commit_media(session, media)
    logger.info(
        "pwa.sync.media_processed",
        extra={
            "tenant_id": str(tenant.id),
            "user_id": str(access.user.id),
            "media_id": str(updated.id),
            "status": updated.upload_status,
        },
    )
    return updated


@router.post("/sync/conflicts/{batch_id}/resolve")
async def resolve_conflict(
    batch_id: str,
    payload: dict[str, Any],
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    access: AccessContext = Depends(rbac()),
):
    strategy = str((payload or {}).get("strategy") or "").strip()
    if strategy not in {"server_wins", "client_retry"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="PWA_SYNC_CONFLICT_STRATEGY_INVALID",
                message="strategy must be one of: server_wins, client_retry",
                error_type="pwa",
            ),
        )
    batch = await OfflineSyncService().get_status(session, batch_id, tenant_id=str(tenant.id))
    if not batch:
        raise HTTPException(404, "Batch not found")
    _ensure_owner_or_admin(access=access, owner_user_id=str(batch.user_id))
    payload_patch = (payload or {}).get("payload_patch")
    if payload_patch is not None and not isinstance(payload_patch, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="PWA_SYNC_CONFLICT_PAYLOAD_PATCH_INVALID",
                message="payload_patch must be an object",
                error_type="pwa",
            ),
        )
    resolved = await OfflineSyncService().resolve_conflict(
        session,
        batch=batch,
        strategy=strategy,
        payload_patch=_sanitize_offline_entity_payload(payload_patch or {}),
    )
    logger.info(
        "pwa.sync.conflict_resolved",
        extra={
            "tenant_id": str(tenant.id),
            "user_id": str(access.user.id),
            "batch_id": str(resolved.id),
            "strategy": strategy,
            "new_status": resolved.status,
        },
    )
    return resolved


async def _resolve_person_id(session: AsyncSession, tenant_id: Any, user_email: Any) -> str | None:
    """Resolve the Person record linked to the authenticated user, or None.

    The bootstrap is the caller's *own* offline dataset, so per-person projections
    (training assignments, compliance deadlines) are scoped to this person. The
    Person↔User link is resolved by case-insensitive email match — the same
    convention already used to surface a person's login account in
    ``EmployeeCardService`` (``backend/app/services/employee_card.py``). A user with
    no matching Person (e.g. an admin without a personnel record) legitimately has
    no personal assignments — callers must NOT fall back to the tenant-wide list,
    which would over-expose every person's data.
    """
    if not user_email:
        return None
    return (
        await session.execute(
            select(Person.id)
            .where(
                Person.tenant_id == tenant_id,
                func.lower(Person.email) == str(user_email).lower(),
                Person.deleted_at.is_(None),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


@router.get("/bootstrap", response_model=PwaBootstrapResponse)
async def bootstrap(
    tenant: Tenant = Depends(get_tenant_record),
    session: AsyncSession = Depends(get_session),
    access: AccessContext = Depends(rbac()),
):
    permissions = _normalize_permissions(access)
    person_id = await _resolve_person_id(session, tenant.id, getattr(access.user, "email", None))
    templates = (
        (
            await session.execute(
                select(BriefingTemplate).where(
                    BriefingTemplate.tenant_id == tenant.id,
                    BriefingTemplate.deleted_at.is_(None),
                    BriefingTemplate.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    journals = (
        (
            await session.execute(
                select(BriefingJournal).where(
                    BriefingJournal.tenant_id == tenant.id,
                    BriefingJournal.deleted_at.is_(None),
                    BriefingJournal.status == "active",
                )
            )
        )
        .scalars()
        .all()
    )
    # Per-person projections are scoped to the caller's own personnel record. With no
    # linked Person the caller has no personal assignments (never the tenant-wide list).
    enrollments: list[TrainingEnrollment] = []
    deadlines: list[ComplianceDeadline] = []
    if person_id is not None:
        enrollments = list(
            (
                await session.execute(
                    select(TrainingEnrollment).where(
                        TrainingEnrollment.tenant_id == tenant.id,
                        TrainingEnrollment.person_id == person_id,
                        TrainingEnrollment.deleted_at.is_(None),
                        TrainingEnrollment.status.in_(["assigned", "in_progress"]),
                    )
                )
            )
            .scalars()
            .all()
        )
        deadlines = list(
            (
                await session.execute(
                    select(ComplianceDeadline).where(
                        ComplianceDeadline.tenant_id == tenant.id,
                        ComplianceDeadline.person_id == person_id,
                        ComplianceDeadline.status.in_(["upcoming", "due", "overdue"]),
                    )
                )
            )
            .scalars()
            .all()
        )
    pending_batches = int(
        (
            await session.execute(
                select(func.count(OfflineSyncBatch.id)).where(
                    OfflineSyncBatch.tenant_id == tenant.id,
                    OfflineSyncBatch.user_id == access.user.id,
                    OfflineSyncBatch.status == "pending",
                )
            )
        ).scalar_one()
        or 0
    )
    failed_batches = int(
        (
            await session.execute(
                select(func.count(OfflineSyncBatch.id)).where(
                    OfflineSyncBatch.tenant_id == tenant.id,
                    OfflineSyncBatch.user_id == access.user.id,
                    OfflineSyncBatch.status == "failed",
                )
            )
        ).scalar_one()
        or 0
    )
    pending_media = int(
        (
            await session.execute(
                select(func.count(OfflineMediaQueue.id)).where(
                    OfflineMediaQueue.tenant_id == tenant.id,
                    OfflineMediaQueue.user_id == access.user.id,
                    OfflineMediaQueue.upload_status == "pending",
                )
            )
        ).scalar_one()
        or 0
    )
    failed_media = int(
        (
            await session.execute(
                select(func.count(OfflineMediaQueue.id)).where(
                    OfflineMediaQueue.tenant_id == tenant.id,
                    OfflineMediaQueue.user_id == access.user.id,
                    OfflineMediaQueue.upload_status == "failed",
                )
            )
        ).scalar_one()
        or 0
    )
    failed_conflicts = (
        (
            await session.execute(
                select(OfflineSyncBatch)
                .where(
                    OfflineSyncBatch.tenant_id == tenant.id,
                    OfflineSyncBatch.user_id == access.user.id,
                    OfflineSyncBatch.status == "failed",
                )
                .order_by(OfflineSyncBatch.updated_at.desc())
            )
        )
        .scalars()
        .all()
    )

    deadlines_by_status: dict[str, int] = {"upcoming": 0, "due": 0, "overdue": 0}
    for item in deadlines:
        deadlines_by_status[item.status] = deadlines_by_status.get(item.status, 0) + 1

    return PwaBootstrapResponse(
        current_user=PwaCurrentUser(
            id=str(access.user.id),
            email=access.user.email,
            role=access.user.role.value,
            roles=access.to_auth_context().roles,
            permissions=permissions,
            company_id=(
                str(access.user.company_id) if getattr(access.user, "company_id", None) else None
            ),
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
        ),
        tenant_branding=PwaTenantBranding(slug=tenant.slug, name=tenant.name),
        route_permissions=_route_permissions(permissions),
        briefing_templates=[_serialize_template(item) for item in templates],
        active_journals=[_serialize_journal(item) for item in journals],
        assigned_training=[_serialize_enrollment(item) for item in enrollments],
        compliance_deadlines_summary={
            "count": len(deadlines),
            "by_status": deadlines_by_status,
            "items": [_serialize_deadline(item).model_dump(mode="json") for item in deadlines[:25]],
            "latest_due_at": _serialize_date(
                min((item.due_at for item in deadlines), default=None)
            ),
        },
        offline_queue={
            "capabilities": _build_offline_capabilities(permissions),
            "failed_conflicts": [
                _serialize_conflict(item).model_dump(mode="json") for item in failed_conflicts[:10]
            ],
            "conflict_count": len(failed_conflicts),
            "draft_entity_types": [
                "briefing_entry",
                "incident",
                "inspection_checklist",
                "task_comment",
                "training_ack",
            ],
            "draft_policy": _build_draft_policy(
                pending_batches=pending_batches, failed_batches=failed_batches
            ),
            "conflict_resolution": _build_conflict_resolution_contract(len(failed_conflicts)),
        },
        dictionaries=_build_dictionaries(),
        sync_state=_build_sync_state(
            pending_batches=pending_batches,
            failed_batches=failed_batches,
            pending_media=pending_media,
            failed_media=failed_media,
        ),
        diagnostics={
            "provider_mode": "projection_api",
            "bootstrap_version": 4,
            "auth_required": True,
            "offline_scope": ["briefings", "training", "tasks", "incidents", "checklists", "media"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "conflict_resolution_required": len(failed_conflicts) > 0,
            "permissions_etag": _permissions_etag(permissions),
            "route_permission_count": len(PWA_ROUTE_PERMISSION_MAP),
            "user_scoped": True,
        },
    )
