from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac_abac import RESOURCE_PERMISSIONS, ROLE_PERMISSIONS
from app.models.models import AuthzPermission, AuthzRole, AuthzRolePermission

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


async def seed_authz_catalog(session: AsyncSession, *, tenant_id: str) -> None:
    """Seed authz catalog (roles, permissions, mappings) for a given tenant.

    ``tenant_id`` is required because ``AuthzRole``/``AuthzPermission``/
    ``AuthzRolePermission`` all extend :class:`AuthzBaseModel` whose
    ``tenant_id`` column is ``NOT NULL``. The legacy ``__tenant_model__``
    auto-fill hook does NOT cover these models, so the caller must pass the
    target tenant explicitly. Role uniqueness is scoped per tenant
    (``uq_authz_roles_tenant_code``); permissions use a global ``code``
    unique constraint, so they are reused across tenants once created.
    """

    role_records: dict[str, AuthzRole] = {}
    for role_code in ROLE_CODES:
        existing = (
            await session.execute(
                select(AuthzRole).where(
                    AuthzRole.tenant_id == tenant_id,
                    AuthzRole.code == role_code,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            existing = AuthzRole(
                code=role_code,
                name=role_code.replace("_", " ").title(),
                tenant_id=tenant_id,
            )
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
                existing = AuthzPermission(
                    resource=resource,
                    action=action,
                    code=code,
                    tenant_id=tenant_id,
                )
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
                        AuthzRolePermission.tenant_id == tenant_id,
                        AuthzRolePermission.role_id == role.id,
                        AuthzRolePermission.permission_code == permission_code,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                session.add(
                    AuthzRolePermission(
                        role_id=role.id,
                        permission_id=permission.id,
                        permission_code=permission_code,
                        tenant_id=tenant_id,
                    )
                )

    await session.flush()
