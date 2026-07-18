"""Admin endpoints for managing user roles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_correlation_id, get_session, get_tenant_record
from app.api.helpers.etag import (
    apply_etag_response_headers,
    build_not_modified_headers,
    compute_list_etag,
)
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.core.security import AccessContext, rbac
from app.core.tenant_validation import TenantContextValidator
from app.models.models import RoleEnum, Tenant, User, UserAttribute, UserRole
from app.schemas.admin_user import (
    UserAttributesRequest,
    UserAttributesResponse,
    UserListItem,
    UserListPage,
    UserRolesRequest,
    UserRolesResponse,
)
from app.services.refresh_sessions import revoke_refresh_sessions_for_user

router = APIRouter()

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)
AdminAccess = Depends(rbac(["admin", "owner"]))


def _admin_user_unprocessable(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=api_problem_detail(
            code="ADMIN_USER_VALIDATION_ERROR",
            message=message,
            error_type="admin",
        ),
    )


def _normalize_roles(roles: list[str]) -> list[RoleEnum]:
    normalized: list[RoleEnum] = []
    for role in roles:
        try:
            normalized.append(RoleEnum(str(role).lower()))
        except ValueError as exc:
            raise _admin_user_unprocessable(f"Unsupported role: {role}") from exc
    deduped = list(dict.fromkeys(normalized))
    return deduped


def _collect_role_values(user: User) -> list[str]:
    roles = [user.role.value]
    roles.extend(role.role.value for role in getattr(user, "roles", []))
    return list(dict.fromkeys(role.lower() for role in roles if role))


@router.get("/admin/users", response_model=UserListPage)
async def list_admin_users(
    request: Request,
    response: Response,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AdminAccess,
    role: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    company_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> UserListPage | Response:
    TenantContextValidator.ensure_tenant_context(tenant)

    role_enum: RoleEnum | None = None
    if role:
        try:
            role_enum = RoleEnum(role.lower())
        except ValueError as exc:
            raise _admin_user_unprocessable(f"Unsupported role: {role}") from exc

    base_where = [User.tenant_id == tenant.id, User.deleted_at.is_(None)]
    if role_enum is not None:
        base_where.append(User.role == role_enum)
    if is_active is not None:
        base_where.append(User.is_active.is_(is_active))
    if company_id:
        base_where.append(User.company_id == company_id)

    total = int(
        await session.scalar(
            select(func.count()).select_from(select(User).where(*base_where).subquery())
        )
        or 0
    )
    rows = list(
        (
            await session.execute(
                select(User)
                .where(*base_where)
                .order_by(User.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    etag = compute_list_etag(
        tenant_id=str(tenant.id),
        items=rows,
        scalars=[
            ("total", total),
            ("limit", limit),
            ("offset", offset),
            ("role", role_enum.value if role_enum else ""),
            ("active", "" if is_active is None else ("1" if is_active else "0")),
            ("company", company_id or ""),
        ],
    )
    apply_etag_response_headers(response, etag)
    if request.headers.get("if-none-match") == etag:
        return Response(
            status_code=status.HTTP_304_NOT_MODIFIED,
            headers=build_not_modified_headers(etag),
        )
    return UserListPage(
        items=[UserListItem.model_validate(user) for user in rows],
        total=total,
    )


@router.get("/admin/users/{user_id}/roles", response_model=UserRolesResponse)
async def get_user_roles(
    user_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AdminAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> UserRolesResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id, User.tenant_id == tenant.id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return UserRolesResponse(user_id=user.id, roles=_collect_role_values(user))


@router.patch("/admin/users/{user_id}/roles", response_model=UserRolesResponse)
@router.post("/admin/users/{user_id}/roles", response_model=UserRolesResponse)
@audit_operation("assign", "user_role")
async def assign_user_roles(
    user_id: str,
    payload: UserRolesRequest,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AdminAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> UserRolesResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id, User.tenant_id == tenant.id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    roles = _normalize_roles(payload.roles)
    if not roles:
        raise _admin_user_unprocessable("At least one role is required")

    user.role = roles[0]
    user.roles.clear()
    for role in roles:
        user.roles.append(UserRole(tenant_id=str(tenant.id), user_id=user.id, role=role))
    await revoke_refresh_sessions_for_user(
        session=session,
        tenant_id=str(tenant.id),
        user_id=user.id,
        reason="role-change",
    )

    await session.commit()
    await session.refresh(user)
    return UserRolesResponse(user_id=user.id, roles=_collect_role_values(user))


@router.patch("/admin/users/{user_id}/attributes", response_model=UserAttributesResponse)
@audit_operation("assign", "user_attribute")
async def assign_user_attributes(
    user_id: str,
    payload: UserAttributesRequest,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AdminAccess,
    correlation_id: str = Depends(get_correlation_id),
) -> UserAttributesResponse:
    TenantContextValidator.ensure_tenant_context(tenant)

    user = (
        await session.execute(
            select(User).where(
                User.id == user_id, User.tenant_id == tenant.id, User.deleted_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    attrs = (
        await session.execute(
            select(UserAttribute).where(
                UserAttribute.user_id == user_id,
                UserAttribute.tenant_id == tenant.id,
            )
        )
    ).scalar_one_or_none()
    if attrs is None:
        attrs = UserAttribute(tenant_id=tenant.id, user_id=user_id)
        session.add(attrs)

    attrs.company_ids = payload.company_ids
    attrs.site_ids = payload.site_ids
    attrs.project_ids = payload.project_ids
    attrs.contractor_ids = payload.contractor_ids
    await session.commit()
    await session.refresh(attrs)
    return UserAttributesResponse(
        user_id=user_id,
        company_ids=attrs.company_ids,
        site_ids=attrs.site_ids,
        project_ids=attrs.project_ids,
        contractor_ids=attrs.contractor_ids,
    )
