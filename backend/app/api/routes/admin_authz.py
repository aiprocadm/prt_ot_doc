from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.modules.rbac_abac.engine import evaluate
from app.modules.rbac_abac.types import PolicyContext, Resource, Subject
from app.models.models import AuthzPolicy, AuthzRole, AuthzRolePermission, AuthzUserRole, Tenant

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
async def create_role(payload: RolePayload, *, tenant: TenantDep, _: AdminAccess, session: SessionDep):
    row = AuthzRole(tenant_id=str(tenant.id), code=payload.code, name=payload.name, is_system=payload.is_system)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.post("/roles/assign")
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
