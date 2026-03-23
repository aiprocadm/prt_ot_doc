"""Authentication routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.rate_limit import ip_subject_key, limiter, login_per_identity
from app.core.rbac_abac import ROLE_PERMISSIONS
from app.core.security import (
    AccessContext,
    issue_access_token,
    issue_refresh_token,
    rbac,
    verify_token,
)
from app.models.models import Tenant, User
from app.services.auth import verify_password
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

router = APIRouter()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(extra="forbid")


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)

    model_config = ConfigDict(extra="forbid")


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str


class MeResponse(BaseModel):
    sub: str
    email: EmailStr
    role: str
    tenant_id: str | None = None
    tenant_slug: str | None = None
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    company_id: str | None = None
    attributes: dict[str, list[str]] = Field(default_factory=dict)
    abac_scopes: dict[str, list[str] | int | None] = Field(default_factory=dict)
    abilities: list[str] = Field(default_factory=list)


class AdminPingResponse(BaseModel):
    status: Literal["ok"]
    user_id: str


class PermissionsResponse(BaseModel):
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    abac_scopes: dict[str, list[str] | int | None] = Field(default_factory=dict)



async def _resolve_login_tenant(request: Request) -> Tenant | None:
    try:
        return await get_tenant_record(request)
    except HTTPException as exc:
        if exc.status_code in {status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND}:
            return None
        raise

def _invalid_credentials() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")


def _invalid_refresh_token() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")


async def _inject_login_subject(
    payload: LoginRequest,
    request: Request,
) -> LoginRequest:
    request.state.rate_limit_subject = payload.email.lower()
    return payload


@router.post("/login", response_model=TokenPair, status_code=status.HTTP_200_OK)
@limiter.limit(lambda: login_per_identity(), key_func=ip_subject_key)
@audit_operation("login", "auth_session")
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest = Depends(_inject_login_subject),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant | None = Depends(_resolve_login_tenant),
) -> TokenPair:
    """Authenticate a user and issue a new token pair."""

    if tenant is None:
        raise _invalid_credentials()

    normalized_email = payload.email.lower()
    getattr(request.state, "rate_limit_subject", None)
    _ = response.headers
    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(
            func.lower(User.email) == normalized_email,
            User.tenant_id == tenant.id,
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _invalid_credentials()

    if not verify_password(payload.password, user.hashed_password):
        raise _invalid_credentials()

    tenant_slug = tenant.slug

    user.last_login_at = datetime.now(timezone.utc)
    await session.commit()

    role_values = _collect_user_roles(user)
    additional_claims: dict[str, Any] = {"tenant_id": user.tenant_id, "roles": role_values}
    if user.company_id:
        additional_claims["company_id"] = str(user.company_id)
    access_token = issue_access_token(
        subject=user.id,
        tenant=tenant_slug,
        role=user.role.value,
        additional_claims=additional_claims,
    )
    refresh_token = issue_refresh_token(
        subject=user.id,
        tenant=tenant_slug,
        role=user.role.value,
        additional_claims=additional_claims,
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.get("/me", response_model=MeResponse, status_code=status.HTTP_200_OK)
async def me(access: AccessContext = Depends(rbac())) -> MeResponse:
    """Return basic profile information for the authenticated subject."""

    context = access.to_auth_context()
    abilities = sorted(
        {perm for role in context.roles for perm in ROLE_PERMISSIONS.get(role, set())}
    )
    permissions = sorted({perm.replace(":", ".") for perm in abilities})
    return MeResponse(
        sub=context.sub,
        email=access.user.email,
        role=access.user.role.value,
        tenant_id=context.tenant_id,
        tenant_slug=access.tenant_slug,
        roles=context.roles,
        permissions=permissions,
        company_id=access.company_id,
        abilities=abilities,
        attributes={
            "company_ids": [str(v) for v in access.claims.get("company_ids", [])],
            "site_ids": [str(v) for v in access.claims.get("site_ids", [])],
            "project_ids": [str(v) for v in access.claims.get("project_ids", [])],
            "contractor_ids": [str(v) for v in access.claims.get("contractor_ids", [])],
        },
        abac_scopes={
            "company_ids": [str(v) for v in access.claims.get("company_ids", [])],
            "site_ids": [str(v) for v in access.claims.get("site_ids", [])],
            "project_ids": [str(v) for v in access.claims.get("project_ids", [])],
            "contractor_ids": [str(v) for v in access.claims.get("contractor_ids", [])],
            "risk_level_max": access.claims.get("max_risk_level"),
        },
    )




@router.get("/me/permissions", response_model=PermissionsResponse, status_code=status.HTTP_200_OK)
async def me_permissions(access: AccessContext = Depends(rbac())) -> PermissionsResponse:
    """Return effective permission codes and ABAC scopes for the authenticated subject."""

    context = access.to_auth_context()
    permissions = sorted({perm.replace(":", ".") for role in context.roles for perm in ROLE_PERMISSIONS.get(role, set())})
    return PermissionsResponse(
        roles=context.roles,
        permissions=permissions,
        abac_scopes={
            "company_ids": [str(v) for v in access.claims.get("company_ids", [])],
            "site_ids": [str(v) for v in access.claims.get("site_ids", [])],
            "project_ids": [str(v) for v in access.claims.get("project_ids", [])],
            "contractor_ids": [str(v) for v in access.claims.get("contractor_ids", [])],
            "risk_level_max": access.claims.get("max_risk_level"),
        },
    )


@router.post("/refresh", response_model=TokenPair, status_code=status.HTTP_200_OK)
@audit_operation("refresh", "auth_session")
async def refresh_tokens(
    payload: RefreshRequest,
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> TokenPair:
    """Validate a refresh token and issue a new token pair."""

    try:
        claims = verify_token(payload.refresh_token, expected_type="refresh")
    except HTTPException as exc:
        raise _invalid_refresh_token() from exc

    subject = claims.get("sub")
    tenant_claim = claims.get("tenant")
    role = claims.get("role")

    if not subject or not tenant_claim or not role:
        raise _invalid_refresh_token()

    session_tenant = str(session.info.get("tenant") or tenant.slug or "").strip()
    if tenant_claim != session_tenant:
        raise _invalid_refresh_token()

    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == subject, User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _invalid_refresh_token()

    additional_claims = {"tenant_id": user.tenant_id, "roles": _collect_user_roles(user)}
    if user.company_id:
        additional_claims["company_id"] = str(user.company_id)
    access_token = issue_access_token(
        subject=user.id,
        tenant=tenant_claim,
        role=user.role.value,
        additional_claims=additional_claims,
    )
    refresh_token = issue_refresh_token(
        subject=user.id,
        tenant=tenant_claim,
        role=user.role.value,
        additional_claims=additional_claims,
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token)


@router.get("/admin/ping", response_model=AdminPingResponse)
async def admin_ping(access: AccessContext = Depends(rbac(["admin", "owner"]))):
    """Simple guard-protected endpoint used to validate RBAC wiring."""

    return AdminPingResponse(status="ok", user_id=access.user.id)


def _collect_user_roles(user: User) -> list[str]:
    roles = [user.role.value]
    roles.extend(role.role.value for role in getattr(user, "roles", []))
    return list(dict.fromkeys(role.lower() for role in roles if role))
