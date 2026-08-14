"""Действующий бренд арендатора для кода вне HTTP (BIZ-52 срез-10).

Маршрут `/public/branding` умел собирать бренд по цепочке наследования, но
делал это внутри себя, и добраться до готового бренда из фоновой отправки писем
было нельзя. Скопировать выборку означало бы завести ВТОРУЮ правду о том, чей
бренд действует: разойдись они однажды — приложение показывало бы одно имя, а
письма подписывались другим, и понять, какое из них верное, стало бы невозможно.

Поэтому выборка живёт здесь одна, а маршрут пользуется ею же.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.domains.reseller.white_label import AppBrand, BrandOverride, resolve_app_brand
from app.models.models import Tenant
from app.models.white_label import TenantBranding


def brand_session() -> AsyncSession:
    """Доверенная сессия общей схемы для чтения бренда.

    ``rls_bypass``: клиенту нужен бренд ЕГО ПАРТНЁРА, а это строка другого
    арендатора — под FORCE RLS (SEC-65) обычная сессия её не увидит, и клиент
    молча получил бы бренд платформы вместо партнёрского. Это не дыра: наружу
    уходят только поля бренда, которые и так показываются каждому, кто открыл
    страницу входа.
    """

    return AsyncSessionLocal(
        tenant="public", include_public=False, create_schema=False, rls_bypass=True
    )


@dataclass(frozen=True)
class BrandRowView:
    """Строка бренда без байтов картинок.

    Байты НЕ выгружаются, когда нужен только признак «картинка есть»: иначе
    каждый показ страницы входа тянул бы из базы до полумегабайта впустую.
    """

    override: BrandOverride
    has_logo: bool
    has_favicon: bool


async def load_brand_row(session: AsyncSession, tenant_id: str) -> BrandRowView | None:
    row = (
        await session.execute(
            select(
                TenantBranding.app_name,
                TenantBranding.primary_color,
                TenantBranding.support_email,
                TenantBranding.logo_image.isnot(None),
                TenantBranding.favicon_image.isnot(None),
            ).where(TenantBranding.tenant_id == tenant_id)
        )
    ).first()
    if row is None:
        return None
    app_name, primary_color, support_email, has_logo, has_favicon = row
    return BrandRowView(
        override=BrandOverride(
            app_name=app_name, primary_color=primary_color, support_email=support_email
        ),
        has_logo=bool(has_logo),
        has_favicon=bool(has_favicon),
    )


async def resolve_effective_brand(
    *, tenant_id: str, parent_id: str | None
) -> tuple[AppBrand, bool, bool]:
    """Действующий бренд плюс признаки картинок.

    Картинки наследуются ПО ОТДЕЛЬНОСТИ, как имя и цвет: у клиента нет своего
    логотипа — показывается логотип партнёра, независимо от того, чьё имя
    победило в текстовых полях.
    """

    async with brand_session() as session:
        own = await load_brand_row(session, tenant_id)
        reseller = await load_brand_row(session, parent_id) if parent_id else None
    brand = resolve_app_brand(
        own=own.override if own else None,
        reseller=reseller.override if reseller else None,
    )
    has_logo = (own.has_logo if own else False) or (reseller.has_logo if reseller else False)
    has_favicon = (own.has_favicon if own else False) or (
        reseller.has_favicon if reseller else False
    )
    return brand, has_logo, has_favicon


async def brand_for_tenant_id(tenant_id: str) -> AppBrand:
    """Действующий бренд по одному идентификатору арендатора.

    Для фоновых задач, у которых нет загруженной строки арендатора. Берём ТОЛЬКО
    `parent_id`, а не всю строку: у `Tenant` есть колонки-перечисления, а под
    доверенной сессией `search_path` пуст, и приведение типа `tenantkind` там
    падает (грабля среза-7). Одно поле обходит это без единого исключения.

    Ненайденный арендатор — бренд платформы, а не отказ: письмо должно уйти даже
    если строка исчезла, просто без партнёрского оформления.
    """

    async with brand_session() as session:
        parent_id = (
            await session.execute(select(Tenant.parent_id).where(Tenant.id == tenant_id))
        ).scalar_one_or_none()
    brand, _, _ = await resolve_effective_brand(tenant_id=tenant_id, parent_id=parent_id)
    return brand
