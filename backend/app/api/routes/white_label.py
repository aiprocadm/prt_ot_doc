"""Бренд приложения: чтение всеми, правка — владельцем платформы и партнёром.

Доп. №1 разд. 52.2. Три ручки:

* ``GET /public/branding`` — действующий бренд, БЕЗ токена. Так и задумано:
  бренд нужен экрану входа, а на нём токена ещё нет. Отдавать после входа
  значит показать человеку сначала вендора, а потом подменить — то есть ровно
  не выполнить требование «скрытие любых упоминаний исходного вендора».
* ``GET /platform/branding`` — своя настройка (что именно задано, а что
  унаследовано).
* ``PUT /platform/branding`` — правка своей настройки.

Правит только владелец платформы или партнёр: разд. 52.2 — про перебрендирование
платформы теми, кто её продаёт. Клиентскому арендатору своя настройка не нужна и
не даётся, а цепочка наследования на это не опирается — появись такое право
позже, менять правила не придётся.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.db.session import AsyncSessionLocal
from app.domains.reseller.white_label import (
    AppBrand,
    BrandOverride,
    resolve_app_brand,
)
from app.models.models import Tenant
from app.models.white_label import TenantBranding
from app.schemas.white_label import AppBrandRead, TenantBrandingPatch, TenantBrandingRead

public_router = APIRouter(prefix="/public/branding", tags=["white-label"])
router = APIRouter(prefix="/platform/branding", tags=["white-label"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _brand_session() -> AsyncSession:
    """Доверенная сессия общей схемы для чтения бренда.

    ``rls_bypass``: клиенту нужен бренд ЕГО ПАРТНЁРА, а это строка другого
    арендатора — под FORCE RLS (SEC-65) обычная сессия её не увидит, и клиент
    молча получил бы бренд платформы вместо партнёрского. Это не дыра: наружу
    уходят только три поля бренда, которые и так показываются каждому, кто
    открыл страницу входа.
    """

    return AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    )


async def _load_override(session: AsyncSession, tenant_id: str) -> BrandOverride | None:
    row = (
        await session.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return BrandOverride(
        app_name=row.app_name,
        primary_color=row.primary_color,
        support_email=row.support_email,
    )


async def _effective_brand(tenant: Tenant) -> AppBrand:
    async with _brand_session() as session:
        own = await _load_override(session, tenant.id)
        reseller = (
            await _load_override(session, str(tenant.parent_id)) if tenant.parent_id else None
        )
    return resolve_app_brand(own=own, reseller=reseller)


@public_router.get("", response_model=AppBrandRead)
async def read_public_branding(tenant: Tenant = Depends(get_tenant_record)) -> AppBrandRead:
    """Бренд, под которым показывать приложение этому арендатору."""

    brand = await _effective_brand(tenant)
    return AppBrandRead(
        app_name=brand.app_name,
        primary_color=brand.primary_color,
        support_email=brand.support_email,
        source=brand.source,
    )


def _require_brand_editor(
    credentials: HTTPAuthorizationCredentials | None, tenant: Tenant
) -> None:
    """Правка бренда — владельцу платформы и партнёру, каждому только своего.

    Проверка переиспользует область флота (BIZ-52 срез-2): кто имеет кабинет,
    тот и брендирует себя. Отдельное правило здесь разъехалось бы с ним при
    первом же изменении уровней.
    """

    from app.api.routes.platform_tenants import _require_fleet_actor

    _require_fleet_actor(credentials, tenant)


@router.get("", response_model=TenantBrandingRead)
async def read_own_branding(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantBrandingRead:
    _require_brand_editor(credentials, tenant)
    row = (
        await session.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    effective = await _effective_brand(tenant)
    return TenantBrandingRead(
        app_name=row.app_name if row else None,
        primary_color=row.primary_color if row else None,
        support_email=row.support_email if row else None,
        effective=AppBrandRead(
            app_name=effective.app_name,
            primary_color=effective.primary_color,
            support_email=effective.support_email,
            source=effective.source,
        ),
    )


@router.put("", response_model=TenantBrandingRead)
@audit_operation("update", "tenant_branding")
async def update_own_branding(
    payload: TenantBrandingPatch,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantBrandingRead:
    """Заменить свою настройку бренда.

    Пустое поле означает «не задано» и возвращает наследование, а не стирает
    бренд в пустоту: партнёр, очистивший имя, обязан снова увидеть имя
    платформы, а не приложение без названия.
    """

    _require_brand_editor(credentials, tenant)
    row = (
        await session.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant.id)
        )
    ).scalar_one_or_none()
    if row is None:
        # update-or-insert, а не add: вторая строка сделала бы ответ ручки
        # неопределённым (грабля BIZ-61 срез-2).
        row = TenantBranding(tenant_id=tenant.id)
        session.add(row)
    row.app_name = payload.app_name
    row.primary_color = payload.primary_color
    row.support_email = payload.support_email
    await session.commit()

    return await read_own_branding(session, tenant, credentials)
