"""Authentication routes."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.config import get_settings
from app.core.csrf import CsrfOriginError, assert_trusted_origin
from app.core.rate_limit import ip_subject_key, limiter, login_per_identity
from app.core.rbac_abac import ROLE_PERMISSIONS
from app.core.security import (
    AccessContext,
    decode_token,
    issue_access_token,
    issue_refresh_token,
    rbac,
    verify_token,
)
from app.core.tenant_validation import TenantContextValidator
from app.domains.managed_clients.delegated_identity import (
    is_delegated_email,
    is_delegated_password,
)
from app.models.models import Tenant, User
from app.services.auth import verify_password
from app.services.refresh_sessions import (
    RefreshSessionError,
    consume_refresh_session,
    create_refresh_session,
    revoke_refresh_sessions_for_user,
)

router = APIRouter()
logger = logging.getLogger(__name__)
settings = get_settings()
REFRESH_COOKIE_NAME = "prt_refresh_token"
REFRESH_COOKIE_PATH = f"{settings.api_v1_prefix}/auth/refresh"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    model_config = ConfigDict(extra="forbid")


class RefreshRequest(BaseModel):
    refresh_token: str | None = Field(default=None, min_length=1)

    model_config = ConfigDict(extra="ignore")


class TokenPair(BaseModel):
    access_token: str


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


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=token,
        max_age=settings.jwt_refresh_ttl_days * 24 * 60 * 60,
        httponly=True,
        secure=True,
        samesite="strict",
        path=REFRESH_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        secure=True,
        samesite="strict",
    )


def _extract_refresh_token(request: Request, payload: RefreshRequest | None) -> str | None:
    cookie_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if cookie_token:
        # SEC-64 (разд. 64.1, CSRF): это единственная мутация, которую браузер может
        # выполнить, не имея доступа к токену, — cookie он подставит сам. SameSite
        # выставляет сервер, а СОБЛЮДАЕТ клиент; Origin проверяет сервер, поэтому
        # это независимый второй рубеж. Проверка только для cookie-пути: у
        # Bearer-запросов подделка невозможна, а серверные клиенты Origin не шлют.
        assert_trusted_origin(request)
        return cookie_token
    if payload and payload.refresh_token:
        return payload.refresh_token
    return None


async def _inject_login_subject(
    payload: LoginRequest,
    request: Request,
) -> LoginRequest:
    request.state.rate_limit_subject = payload.email.lower()
    return payload


@router.post(
    "/login",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Unauthorized"}},
)
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

    TenantContextValidator.ensure_tenant_context(tenant)

    if tenant is None:
        raise _invalid_credentials()

    normalized_email = payload.email.lower()
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

    # BIZ-49 (разд. 49.3): у личности специалиста аутсорсера, заведённой в
    # контуре клиента, пароля НЕТ вовсе. Проверка стоит здесь явно, а не
    # держится на том, что метка не сойдётся с хэшем: случайная защита
    # исчезает при первой же смене хэшера. Ответ тот же, что и при неверном
    # пароле, — существование такой личности посторонним знать незачем.
    if is_delegated_email(user.email) or is_delegated_password(user.hashed_password):
        raise _invalid_credentials()

    # Argon2 — умышленно дорогой CPU-bound верифай (~75+ мс): синхронный вызов
    # в async-обработчике замораживал event loop на КАЖДЫЙ логин, и всплеск
    # логинов серийно стопорил все запросы воркера (perf-smoke: p50 4.4s).
    # argon2-cffi отпускает GIL — в threadpool верифаи идут параллельно.
    if not await run_in_threadpool(verify_password, payload.password, user.hashed_password):
        raise _invalid_credentials()

    tenant_slug = tenant.slug

    # No commit here: it would end the transaction and drop the transaction-local RLS
    # GUCs (SEC-65), so the refresh-session INSERT below — which only lands on the
    # commit at the end of this handler — would be evaluated without a tenant context.
    # ``last_login_at`` rides along on that same final commit.
    #
    # Core-UPDATE вместо ORM-присваивания: у моделей оптимистичная блокировка
    # (version_id_col), и ДВА одновременных логина одного пользователя гонялись
    # за счётчиком версии — проигравший падал StaleDataError → 500 (две вкладки,
    # даблклик, perf-smoke). Для телеметрийного поля верна семантика
    # «последняя запись побеждает», версию не трогаем.
    await session.execute(
        update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc))
    )

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
        additional_claims={**additional_claims, "family_id": str(uuid4())},
    )
    refresh_claims = decode_token(refresh_token)
    await create_refresh_session(
        session=session,
        tenant_id=str(tenant.id),
        user_id=user.id,
        token_jti=str(refresh_claims["jti"]),
        family_id=str(refresh_claims["family_id"]),
        expires_at=datetime.fromtimestamp(int(refresh_claims["exp"]), tz=timezone.utc),
    )
    await session.commit()
    _set_refresh_cookie(response, refresh_token)
    return TokenPair(access_token=access_token)


@router.get(
    "/me",
    response_model=MeResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Unauthorized"}},
)
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


@router.get(
    "/me/permissions",
    response_model=PermissionsResponse,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Unauthorized"}},
)
async def me_permissions(access: AccessContext = Depends(rbac())) -> PermissionsResponse:
    """Return effective permission codes and ABAC scopes for the authenticated subject."""

    context = access.to_auth_context()
    permissions = sorted(
        {
            perm.replace(":", ".")
            for role in context.roles
            for perm in ROLE_PERMISSIONS.get(role, set())
        }
    )
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


@router.post(
    "/refresh",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    responses={status.HTTP_401_UNAUTHORIZED: {"description": "Unauthorized"}},
)
@audit_operation("refresh", "auth_session")
async def refresh_tokens(
    request: Request,
    response: Response,
    payload: RefreshRequest | None = Body(default=None),
    session: AsyncSession = Depends(get_session),
    tenant: Tenant = Depends(get_tenant_record),
) -> TokenPair:
    """Validate a refresh token and issue a new token pair."""

    TenantContextValidator.ensure_tenant_context(tenant)

    try:
        provided_token = _extract_refresh_token(request, payload)
        if not provided_token:
            raise _invalid_refresh_token()
        claims = verify_token(provided_token, expected_type="refresh")
    except CsrfOriginError:
        # Отказ по Origin НЕ схлопываем в 401: иначе попытку CSRF не отличить от
        # обычной истёкшей сессии ни в ответе, ни в логах.
        raise
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
    family_id = str(claims.get("family_id") or "").strip()
    if not family_id:
        raise _invalid_refresh_token()

    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == subject, User.tenant_id == tenant.id)
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise _invalid_refresh_token()
    try:
        current_refresh_session = await consume_refresh_session(
            session=session,
            tenant_id=str(tenant.id),
            user_id=user.id,
            token_jti=str(claims["jti"]),
            family_id=family_id,
        )
    except RefreshSessionError as exc:
        await session.commit()
        logger.warning(
            "auth.refresh.reuse_detected",
            extra={
                "tenant_id": str(tenant.id),
                "user_id": user.id,
                "family_id": family_id,
                "token_jti": claims.get("jti"),
                "reason": exc.reason,
            },
        )
        raise _invalid_refresh_token() from exc

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
        additional_claims={**additional_claims, "family_id": family_id},
    )
    new_refresh_claims = decode_token(refresh_token)
    await create_refresh_session(
        session=session,
        tenant_id=str(tenant.id),
        user_id=user.id,
        token_jti=str(new_refresh_claims["jti"]),
        family_id=family_id,
        expires_at=datetime.fromtimestamp(int(new_refresh_claims["exp"]), tz=timezone.utc),
        parent_jti=str(claims["jti"]),
    )
    current_refresh_session.replaced_by_token_jti = str(new_refresh_claims["jti"])
    await session.commit()
    _set_refresh_cookie(response, refresh_token)
    return TokenPair(access_token=access_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
@audit_operation("logout", "auth_session")
async def logout(
    response: Response,
    access: AccessContext = Depends(rbac()),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await revoke_refresh_sessions_for_user(
        session=session,
        tenant_id=str(access.tenant_id),
        user_id=access.user.id,
        reason="logout",
    )
    await session.commit()
    _clear_refresh_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/admin/ping", response_model=AdminPingResponse)
async def admin_ping(access: AccessContext = Depends(rbac(["admin", "owner"]))):
    """Simple guard-protected endpoint used to validate RBAC wiring."""

    return AdminPingResponse(status="ok", user_id=access.user.id)


def _collect_user_roles(user: User) -> list[str]:
    roles = [user.role.value]
    roles.extend(role.role.value for role in getattr(user, "roles", []))
    return list(dict.fromkeys(role.lower() for role in roles if role))
