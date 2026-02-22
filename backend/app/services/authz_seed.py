from __future__ import annotations

from app.core.rbac_abac import RESOURCE_PERMISSIONS, ROLE_PERMISSIONS
from app.models.models import AuthzPermission, AuthzRole, AuthzRolePermission
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROLE_CODES = [
    "owner",
    "admin",
    "methodist",
    "project_manager",
    "executor",
    "clerk",
    "instructor",
    "student",
    "hse_head",
    "hse_specialist",
    "fire_engineer",
    "ecologist",
    "hr",
    "accountant",
    "lawyer",
    "line_manager",
    "client",
    "auditor_ro",
    "inspector_contractor",
]


async def seed_authz_catalog(session: AsyncSession) -> None:
    role_records: dict[str, AuthzRole] = {}
    for role_code in ROLE_CODES:
        existing = (
            await session.execute(select(AuthzRole).where(AuthzRole.code == role_code))
        ).scalar_one_or_none()
        if existing is None:
            existing = AuthzRole(code=role_code, name=role_code.replace("_", " ").title())
            session.add(existing)
            await session.flush()
        role_records[role_code] = existing

    permission_records: dict[str, AuthzPermission] = {}
    for resource, actions in RESOURCE_PERMISSIONS.items():
        for action in actions:
            code = f"{resource}:{action}"
            existing = (
                await session.execute(select(AuthzPermission).where(AuthzPermission.code == code))
            ).scalar_one_or_none()
            if existing is None:
                existing = AuthzPermission(resource=resource, action=action, code=code)
                session.add(existing)
                await session.flush()
            permission_records[code] = existing

    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        role = role_records.get(role_code)
        if role is None:
            continue
        for permission_code in permission_codes:
            permission = permission_records.get(permission_code)
            if permission is None:
                continue
            exists = (
                await session.execute(
                    select(AuthzRolePermission).where(
                        AuthzRolePermission.role_id == role.id,
                        AuthzRolePermission.permission_id == permission.id,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(AuthzRolePermission(role_id=role.id, permission_id=permission.id))

    await session.flush()
