"""Admin endpoints for managing user roles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.security import AccessContext, rbac
from app.models.models import RoleEnum, Tenant, User, UserRole
from app.schemas.admin_user import UserRolesRequest, UserRolesResponse

router = APIRouter()

SessionDep = Depends(get_session)
TenantDep = Depends(get_tenant_record)
AdminAccess = Depends(rbac(["admin"]))


def _normalize_roles(roles: list[str]) -> list[RoleEnum]:
    normalized: list[RoleEnum] = []
    for role in roles:
        try:
            normalized.append(RoleEnum(str(role).lower()))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported role: {role}",
            ) from exc
    deduped = list(dict.fromkeys(normalized))
    return deduped


def _collect_role_values(user: User) -> list[str]:
    roles = [user.role.value]
    roles.extend(role.role.value for role in getattr(user, "roles", []))
    return list(dict.fromkeys(role.lower() for role in roles if role))


@router.get("/admin/users/{user_id}/roles", response_model=UserRolesResponse)
async def get_user_roles(
    user_id: str,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AdminAccess,
) -> UserRolesResponse:
    result = await session.execute(
        select(User)
        .options(selectinload(User.roles))
        .where(User.id == user_id, User.tenant_id == tenant.id, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    return UserRolesResponse(user_id=user.id, roles=_collect_role_values(user))


@router.post("/admin/users/{user_id}/roles", response_model=UserRolesResponse)
async def assign_user_roles(
    user_id: str,
    payload: UserRolesRequest,
    session: AsyncSession = SessionDep,
    tenant: Tenant = TenantDep,
    _: AccessContext = AdminAccess,
) -> UserRolesResponse:
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
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "At least one role is required")

    user.role = roles[0]
    user.roles.clear()
    for role in roles:
        user.roles.append(UserRole(tenant_id=str(tenant.id), user_id=user.id, role=role))

    await session.commit()
    await session.refresh(user)
    return UserRolesResponse(user_id=user.id, roles=_collect_role_values(user))
