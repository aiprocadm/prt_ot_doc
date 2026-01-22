"""Authentication routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.rate_limit import ip_subject_key, limiter, login_per_identity
from app.core.security import (
    AccessContext,
    issue_access_token,
    issue_refresh_token,
    rbac,
    verify_token,
)
from app.models.models import Tenant, User
from app.services.auth import verify_password

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
    company_id: str | None = None


class AdminPingResponse(BaseModel):
    status: Literal["ok"]
    user_id: str


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
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest = Depends(_inject_login_subject),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> TokenPair:
    """Authenticate a user and issue a new token pair."""

    normalized_email = payload.email.lower()
    getattr(request.state, "rate_limit_subject", None)
    _ = response.headers
    result = await session.execute(
        select(User).where(
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

    additional_claims: dict[str, Any] = {"tenant_id": user.tenant_id}
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
    return MeResponse(
        sub=context.sub,
        email=access.user.email,
        role=access.user.role.value,
        tenant_id=context.tenant_id,
        tenant_slug=access.tenant_slug,
        roles=context.roles,
        company_id=access.company_id,
    )

@router.post("/refresh", response_model=TokenPair, status_code=status.HTTP_200_OK)
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
        select(User).where(User.id == subject, User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _invalid_refresh_token()

    additional_claims = {"tenant_id": user.tenant_id}
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
async def admin_ping(access: AccessContext = Depends(rbac(["admin"]))):
    """Simple guard-protected endpoint used to validate RBAC wiring."""

    return AdminPingResponse(status="ok", user_id=access.user.id)
