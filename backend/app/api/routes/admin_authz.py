from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.security import AccessContext, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.job_engine import DocumentJob, DocumentJobStatus, OutboxEvent, OutboxEventStatus
from app.models.models import (
    AuthzPolicy,
    AuthzRole,
    AuthzRolePermission,
    AuthzUserRole,
    Outbox,
    OutboxStatus,
    Tenant,
)
from app.modules.rbac_abac.engine import evaluate
from app.modules.rbac_abac.types import PolicyContext, Resource, Subject
from app.services.provider_registry import describe_provider

router = APIRouter(prefix="/admin", tags=["admin-rbac-abac"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[Tenant, Depends(get_tenant_record)]
AdminAccess = Annotated[AccessContext, Depends(rbac(["admin", "owner"]))]


class RolePayload(BaseModel):
    code: str
    name: str
    is_system: bool = False


class AssignRolePayload(BaseModel):
    user_id: str
    role_id: str
    scope_json: dict[str, Any] = Field(default_factory=dict)


class PolicyPayload(BaseModel):
    resource: str
    action: str
    effect: str
    conditions_json: dict[str, Any] = Field(default_factory=dict)
    priority: int = 100
    enabled: bool = True


class EvaluatePayload(BaseModel):
    resource: str
    action: str
    attrs: dict[str, Any] = Field(default_factory=dict)


@router.get("/roles")
async def list_roles(*, tenant: TenantDep, _: AdminAccess, session: SessionDep):
    rows = (await session.execute(select(AuthzRole).where(AuthzRole.tenant_id == str(tenant.id)))).scalars().all()
    return rows


@router.post("/roles", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "authz_role")
async def create_role(payload: RolePayload, *, tenant: TenantDep, _: AdminAccess, session: SessionDep):
    row = AuthzRole(tenant_id=str(tenant.id), code=payload.code, name=payload.name, is_system=payload.is_system)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/roles/assign")
@audit_operation("assign", "authz_user_role")
async def assign_role(payload: AssignRolePayload, *, tenant: TenantDep, _: AdminAccess, session: SessionDep):
    row = AuthzUserRole(
        tenant_id=str(tenant.id),
        user_id=payload.user_id,
        role_id=payload.role_id,
        scope_json=payload.scope_json,
    )
    session.add(row)
    await session.commit()
    return {"status": "ok", "id": row.id}


@router.get("/policies")
async def list_policies(*, tenant: TenantDep, _: AdminAccess, session: SessionDep):
    rows = (
        await session.execute(
            select(AuthzPolicy).where(AuthzPolicy.tenant_id == str(tenant.id)).order_by(AuthzPolicy.priority.asc())
        )
    ).scalars().all()
    return rows


@router.post("/policies", status_code=status.HTTP_201_CREATED)
@audit_operation("create", "authz_policy")
async def create_policy(payload: PolicyPayload, *, tenant: TenantDep, _: AdminAccess, session: SessionDep):
    row = AuthzPolicy(tenant_id=str(tenant.id), **payload.model_dump())
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/policies:evaluate")
async def eval_policy(payload: EvaluatePayload, *, tenant: TenantDep, access: AdminAccess, session: SessionDep):
    role_rows = (
        await session.execute(
            select(AuthzUserRole, AuthzRole)
            .join(AuthzRole, AuthzRole.id == AuthzUserRole.role_id)
            .where(AuthzUserRole.tenant_id == str(tenant.id), AuthzUserRole.user_id == str(access.user.id))
        )
    ).all()
    scopes = [row[0].scope_json for row in role_rows]
    perms = (
        await session.execute(
            select(AuthzRolePermission.permission_code)
            .join(AuthzUserRole, AuthzUserRole.role_id == AuthzRolePermission.role_id)
            .where(AuthzUserRole.tenant_id == str(tenant.id), AuthzUserRole.user_id == str(access.user.id))
        )
    ).scalars().all()
    policies = (
        await session.execute(
            select(AuthzPolicy).where(AuthzPolicy.tenant_id == str(tenant.id), AuthzPolicy.enabled.is_(True))
        )
    ).scalars().all()
    subject = Subject(
        user_id=str(access.user.id),
        tenant_id=str(tenant.id),
        roles=tuple(str(item[1].code).lower() for item in role_rows),
        permissions=tuple(str(code).lower() for code in perms),
        company_ids=tuple({v for scope in scopes for v in scope.get("company_ids", [])}),
        site_ids=tuple({v for scope in scopes for v in scope.get("site_ids", [])}),
        project_ids=tuple({v for scope in scopes for v in scope.get("project_ids", [])}),
        contractor_ids=tuple({v for scope in scopes for v in scope.get("contractor_ids", [])}),
    )
    decision = evaluate(
        subject,
        action=payload.action,
        resource=Resource(resource_type=payload.resource, attrs=payload.attrs),
        context=PolicyContext(
            tenant_id=str(tenant.id),
            user_id=str(access.user.id),
            roles=subject.roles,
            permissions=subject.permissions,
            abac_scopes={
                "company_ids": list(subject.company_ids),
                "site_ids": list(subject.site_ids),
                "project_ids": list(subject.project_ids),
                "contractor_ids": list(subject.contractor_ids),
            },
            request_attrs={"policies": policies},
        ),
    )
    return {"allow": decision.allow, "reason": decision.reason, "matched_policy_id": decision.matched_policy_id}


# ---------------------------------------------------------------------------
# OPS-005: Provider Status  GET /admin/provider-status
# ---------------------------------------------------------------------------

_KNOWN_PROVIDERS = [
    ("signing", "internal-fallback"),
    ("edo", "stub-edo"),
    ("accounting", "stub-1c"),
    ("websocket", "polling_fallback"),
    ("frdo", "stub-frdo"),
    ("eisot", "stub-eisot"),
]


class ProviderStatusItem(BaseModel):
    name: str
    adapter: str
    mode: str
    production_ready: bool
    warning: str | None = None


class ProviderStatusResponse(BaseModel):
    generated_at: datetime
    production_ready: bool
    providers: list[ProviderStatusItem]
    blocking_for_golive: list[str]


@router.get("/provider-status", response_model=ProviderStatusResponse, tags=["admin-diagnostics"])
async def get_provider_status(
    _: AdminAccess,
    tenant: TenantDep,
) -> ProviderStatusResponse:
    """Return current operational mode for all platform providers (production vs stub/non-production)."""
    TenantContextValidator.ensure_tenant_context(tenant)
    providers: list[ProviderStatusItem] = []
    blocking: list[str] = []
    for name, adapter_code in _KNOWN_PROVIDERS:
        descriptor = describe_provider(adapter_code)
        providers.append(
            ProviderStatusItem(
                name=name,
                adapter=adapter_code,
                mode=descriptor.mode,
                production_ready=descriptor.production_ready,
                warning=descriptor.warning,
            )
        )
        if not descriptor.production_ready:
            blocking.append(name)
    return ProviderStatusResponse(
        generated_at=datetime.now(timezone.utc),
        production_ready=len(blocking) == 0,
        providers=providers,
        blocking_for_golive=blocking,
    )


# ---------------------------------------------------------------------------
# OPS-004: Tenant Health Score  GET /admin/tenant-health
# ---------------------------------------------------------------------------

class TenantHealthResponse(BaseModel):
    generated_at: datetime
    score: int = Field(ge=0, le=100, description="Composite tenant health score 0-100")
    grade: str = Field(description="A/B/C/D/F")
    failed_jobs_last24h: int
    outbox_pending: int
    outbox_failed: int
    outbox_events_poisoned: int
    non_production_providers: int
    blocking_providers: list[str]
    recommendations: list[str]


@router.get("/tenant-health", response_model=TenantHealthResponse, tags=["admin-diagnostics"])
async def get_tenant_health(
    _: AdminAccess,
    tenant: TenantDep,
    session: SessionDep,
) -> TenantHealthResponse:
    """Composite health score for the tenant: jobs, outbox, provider readiness."""
    TenantContextValidator.ensure_tenant_context(tenant)
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    failed_jobs = int(
        (
            await session.execute(
                select(func.count())
                .select_from(DocumentJob)
                .where(
                    DocumentJob.tenant_id == str(tenant.id),
                    DocumentJob.status == DocumentJobStatus.FAILED.value,
                    DocumentJob.created_at >= since,
                )
            )
        ).scalar_one() or 0
    )

    outbox_counts = (
        await session.execute(
            select(
                func.sum(case((Outbox.status == OutboxStatus.PENDING, 1), else_=0)),
                func.sum(case((Outbox.status == OutboxStatus.FAILED, 1), else_=0)),
            ).where(Outbox.tenant_id == tenant.id)
        )
    ).one()
    outbox_pending = int(outbox_counts[0] or 0)
    outbox_failed = int(outbox_counts[1] or 0)

    events_poisoned = int(
        (
            await session.execute(
                select(func.count())
                .select_from(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant.id,
                    OutboxEvent.status == OutboxEventStatus.POISONED.value,
                )
            )
        ).scalar_one() or 0
    )

    non_prod_providers = [name for name, adapter in _KNOWN_PROVIDERS if not describe_provider(adapter).production_ready]

    # Score calculation: start at 100, deduct for each issue
    score = 100
    recs: list[str] = []
    if failed_jobs > 0:
        deduction = min(20, failed_jobs * 5)
        score -= deduction
        recs.append(f"Resolve {failed_jobs} failed document job(s) in the last 24h")
    if outbox_failed > 0:
        deduction = min(20, outbox_failed * 4)
        score -= deduction
        recs.append(f"Retry or investigate {outbox_failed} failed outbox message(s)")
    if events_poisoned > 0:
        score -= min(15, events_poisoned * 5)
        recs.append(f"Clear {events_poisoned} poisoned outbox event(s)")
    if non_prod_providers:
        score -= min(30, len(non_prod_providers) * 5)
        recs.append(f"Configure production adapters for: {', '.join(non_prod_providers)}")
    if outbox_pending > 50:
        score -= 5
        recs.append(f"High outbox backlog ({outbox_pending} pending) — check delivery workers")

    score = max(0, score)
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 60:
        grade = "C"
    elif score >= 40:
        grade = "D"
    else:
        grade = "F"

    if not recs:
        recs.append("No critical issues detected")

    return TenantHealthResponse(
        generated_at=now,
        score=score,
        grade=grade,
        failed_jobs_last24h=failed_jobs,
        outbox_pending=outbox_pending,
        outbox_failed=outbox_failed,
        outbox_events_poisoned=events_poisoned,
        non_production_providers=len(non_prod_providers),
        blocking_providers=non_prod_providers,
        recommendations=recs,
    )
