"""Development-only bootstrap routines."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db import ensure_tenant_schema, session_scope
from app.models.models import RoleEnum, Tenant, User
from app.modules.subscription.plans import PLANS
from app.services.auth import hash_password
from app.services.tenants.subscription import provision_plan

logger = logging.getLogger(__name__)


async def create_test_user(
    *,
    session: AsyncSession,
    tenant_id: str,
    email: str,
    role: RoleEnum,
    full_name: str | None = None,
    password: str = "test-password",
    is_active: bool = True,
) -> User:
    """Test-only helper: create a User with the given role in the given tenant.

    Used by integration tests under ``tests/`` to seed role-fixtures. Not
    intended for production code paths — callers are expected to commit
    the session themselves so multiple fixtures can be batched.
    """

    user = User(
        tenant_id=tenant_id,
        email=email.lower(),
        full_name=full_name or f"Test user {email}",
        role=role,
        hashed_password=hash_password(password),
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    return user


async def bootstrap_admin_user(settings: Settings) -> None:
    """Create admin user for local/dev environments based on env variables."""

    if not settings.admin_bootstrap:
        return
    if settings.app_env not in {"development", "test"}:
        logger.warning(
            "admin.bootstrap.skipped", extra={"reason": "not-dev", "env": settings.app_env}
        )
        return
    if not settings.admin_password.strip():
        logger.warning("admin.bootstrap.skipped", extra={"reason": "empty-password"})
        return

    tenant_slug = settings.admin_tenant.strip() or settings.default_tenant_slug

    tenant_id: str
    tenant_schema_name: str
    async with session_scope(tenant="public") as session:
        tenant = (
            await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))
        ).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                slug=tenant_slug,
                code=tenant_slug,  # RB-002g: tenant.code is NOT NULL in PG migration
                name=f"{tenant_slug.title()} tenant",
                contact_email=settings.admin_email,
                schema_name=f"tenant_{tenant_slug}",
                is_active=True,
            )
            session.add(tenant)
            await session.flush()
        tenant_id = tenant.id
        tenant_schema_name = str(tenant.schema_name or f"tenant_{tenant_slug}")

        # Тариф разработческого арендатора — «всё включено» (BIZ-53 срез-1).
        # Без выдачи он рождался БЕЗ единой строки, а умолчание продаваемого
        # модуля «выключен»: разработчик поднимал стенд, видел все пункты меню
        # (у роли админа есть все права) и получал 404 на девяти модулях,
        # которые сам же и пишет. Это не продажа: функция целиком работает
        # только при `app_env=dev` — в проде она выходит выше по коду.
        await provision_plan(session, tenant_id=tenant_id, plan=PLANS["enterprise"])

    ensure_tenant_schema(tenant_slug, schema_name=tenant_schema_name)

    async with session_scope(tenant=tenant_slug) as session:
        existing = (
            await session.execute(
                select(User).where(
                    User.tenant_id == tenant_id,
                    func.lower(User.email) == settings.admin_email.lower(),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("Admin created/exists: %s", settings.admin_email)
            return

        user = User(
            tenant_id=tenant_id,
            email=settings.admin_email.lower(),
            full_name="Development Administrator",
            role=RoleEnum.ADMIN,
            hashed_password=hash_password(settings.admin_password),
            is_active=True,
        )
        session.add(user)
        await session.flush()
        logger.info("Admin created/exists: %s", settings.admin_email)
