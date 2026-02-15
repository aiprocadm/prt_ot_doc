"""Development-only bootstrap routines."""

from __future__ import annotations

import logging

from sqlalchemy import func, select

from app.core.config import Settings
from app.db import ensure_tenant_schema, session_scope
from app.models.models import RoleEnum, Tenant, User
from app.services.auth import hash_password

logger = logging.getLogger(__name__)


async def bootstrap_admin_user(settings: Settings) -> None:
    """Create admin user for local/dev environments based on env variables."""

    if not settings.admin_bootstrap:
        return
    if settings.app_env not in {"development", "test"}:
        logger.warning("admin.bootstrap.skipped", extra={"reason": "not-dev", "env": settings.app_env})
        return
    if not settings.admin_password.strip():
        logger.warning("admin.bootstrap.skipped", extra={"reason": "empty-password"})
        return

    tenant_slug = settings.admin_tenant.strip() or settings.default_tenant_slug

    tenant_id: str
    async with session_scope(tenant="public") as session:
        tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalar_one_or_none()
        if tenant is None:
            tenant = Tenant(
                slug=tenant_slug,
                name=f"{tenant_slug.title()} tenant",
                contact_email=settings.admin_email,
                is_active=True,
            )
            session.add(tenant)
            await session.flush()
        tenant_id = tenant.id

    ensure_tenant_schema(tenant_slug)

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
