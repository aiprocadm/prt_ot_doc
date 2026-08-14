"""Бренд приложения: чтение всеми, правка — владельцем платформы и партнёром.

Доп. №1 разд. 52.2. Ручки:

* ``GET /public/branding`` — действующий бренд, БЕЗ токена. Так и задумано:
  бренд нужен экрану входа, а на нём токена ещё нет. Отдавать после входа
  значит показать человеку сначала вендора, а потом подменить — то есть ровно
  не выполнить требование «скрытие любых упоминаний исходного вендора».
* ``GET /public/branding/logo`` и ``/favicon`` — сами картинки, тоже без
  токена и по той же причине.
* ``GET /platform/branding`` — своя настройка (что именно задано, а что
  унаследовано).
* ``PUT /platform/branding`` — правка текстовых полей; ``PUT``/``DELETE``
  ``/platform/branding/logo`` и ``/favicon`` — картинки.

Правит только владелец платформы или партнёр: разд. 52.2 — про перебрендирование
платформы теми, кто её продаёт. Клиентскому арендатору своя настройка не нужна и
не даётся, а цепочка наследования на это не опирается — появись такое право
позже, менять правила не придётся.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.errors import api_problem_detail
from app.domains.reseller.brand_images import (
    FAVICON_MAX_BYTES,
    FAVICON_MEDIA_TYPES,
    LOGO_MAX_BYTES,
    LOGO_MEDIA_TYPES,
    detect_image_media_type,
)
from app.domains.reseller.white_label import AppBrand
from app.models.models import Tenant
from app.models.white_label import TenantBranding
from app.schemas.white_label import AppBrandRead, TenantBrandingPatch, TenantBrandingRead
from app.services.app_branding import (
    brand_session,
    load_brand_row,
    resolve_effective_brand,
)

public_router = APIRouter(prefix="/public/branding", tags=["white-label"])
router = APIRouter(prefix="/platform/branding", tags=["white-label"])
_optional_bearer = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


#: Выборка бренда живёт в `services/app_branding.py` и здесь только
#: переиспользуется: письма (срез-10) обязаны подписываться ТЕМ ЖЕ брендом,
#: который показывает приложение. Две копии выборки однажды разошлись бы, и
#: понять, какое из двух имён верное, стало бы невозможно.
_brand_session = brand_session
_load_view = load_brand_row


async def _effective_view(tenant: Tenant) -> tuple[AppBrand, bool, bool]:
    return await resolve_effective_brand(
        tenant_id=tenant.id,
        parent_id=str(tenant.parent_id) if tenant.parent_id else None,
    )


def _as_brand_read(brand: AppBrand, has_logo: bool, has_favicon: bool) -> AppBrandRead:
    return AppBrandRead(
        app_name=brand.app_name,
        primary_color=brand.primary_color,
        support_email=brand.support_email,
        source=brand.source,
        has_logo=has_logo,
        has_favicon=has_favicon,
    )


@public_router.get("", response_model=AppBrandRead)
async def read_public_branding(tenant: Tenant = Depends(get_tenant_record)) -> AppBrandRead:
    """Бренд, под которым показывать приложение этому арендатору."""

    brand, has_logo, has_favicon = await _effective_view(tenant)
    return _as_brand_read(brand, has_logo, has_favicon)


async def _serve_brand_image(request: Request, tenant: Tenant, *, kind: str) -> Response:
    """Отдать действующую картинку: своя → партнёра → 404.

    Тип содержимого берётся из НАШЕГО распознавания при загрузке, а не из
    заголовка загрузившего; ``nosniff`` запрещает браузеру угадывать сверх
    этого. ETag считается от байтов: favicon запрашивается на каждый заход,
    и без 304 каждый заход стоил бы полной перекачки.
    """

    image_col = TenantBranding.logo_image if kind == "logo" else TenantBranding.favicon_image
    media_col = (
        TenantBranding.logo_media_type if kind == "logo" else TenantBranding.favicon_media_type
    )
    candidates = [tenant.id]
    if tenant.parent_id:
        candidates.append(str(tenant.parent_id))

    async with _brand_session() as session:
        for tenant_id in candidates:
            row = (
                await session.execute(
                    select(image_col, media_col).where(TenantBranding.tenant_id == tenant_id)
                )
            ).first()
            if row is None or not row[0]:
                continue
            data = bytes(row[0])
            etag = f'"{sha256(data).hexdigest()[:16]}"'
            headers = {
                "ETag": etag,
                "Cache-Control": "public, max-age=300",
                "X-Content-Type-Options": "nosniff",
            }
            if request.headers.get("if-none-match") == etag:
                return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
            return Response(
                content=data,
                media_type=row[1] or "application/octet-stream",
                headers=headers,
            )
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Картинка не задана")


@public_router.get("/logo")
async def read_public_logo(
    request: Request, tenant: Tenant = Depends(get_tenant_record)
) -> Response:
    return await _serve_brand_image(request, tenant, kind="logo")


@public_router.get("/favicon")
async def read_public_favicon(
    request: Request, tenant: Tenant = Depends(get_tenant_record)
) -> Response:
    return await _serve_brand_image(request, tenant, kind="favicon")


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
    # Своя строка читается сессией запроса: она видна под RLS без обхода.
    own = await _load_view(session, tenant.id)
    brand, has_logo, has_favicon = await _effective_view(tenant)
    return TenantBrandingRead(
        app_name=own.override.app_name if own else None,
        primary_color=own.override.primary_color if own else None,
        support_email=own.override.support_email if own else None,
        has_logo=own.has_logo if own else False,
        has_favicon=own.has_favicon if own else False,
        effective=_as_brand_read(brand, has_logo, has_favicon),
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


async def _own_row(session: AsyncSession, tenant_id: str) -> TenantBranding | None:
    return (
        await session.execute(
            select(TenantBranding).where(TenantBranding.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def _read_limited(file: UploadFile, max_bytes: int, *, kind: str) -> bytes:
    """Прочитать не больше потолка. Потолок проверяется по ФАКТУ чтения.

    Заявленный размер (`Content-Length`) — такая же строка клиента, как и тип:
    проверка только по нему пропустила бы поток, который врёт о своей длине.
    Читаем на байт больше потолка — если байт нашёлся, файл велик, сколько бы
    он ни «заявлял».
    """

    data = await file.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=api_problem_detail(
                code="BRAND_IMAGE_TOO_LARGE",
                message=f"Картинка «{kind}» больше потолка в {max_bytes // 1024} КБ",
                error_type="white-label",
            ),
        )
    return data


def _sniff_or_reject(data: bytes, allowed: frozenset[str], *, kind: str) -> str:
    media_type = detect_image_media_type(data)
    if media_type is None or media_type not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=api_problem_detail(
                code="BRAND_IMAGE_FORMAT_UNSUPPORTED",
                message=(
                    f"Для «{kind}» принимаются только {', '.join(sorted(allowed))}; "
                    "формат определяется по содержимому файла"
                ),
                error_type="white-label",
            ),
        )
    return media_type


async def _store_image(
    session: AsyncSession,
    tenant: Tenant,
    file: UploadFile,
    *,
    kind: str,
) -> None:
    if kind == "logo":
        data = await _read_limited(file, LOGO_MAX_BYTES, kind=kind)
        media_type = _sniff_or_reject(data, LOGO_MEDIA_TYPES, kind=kind)
    else:
        data = await _read_limited(file, FAVICON_MAX_BYTES, kind=kind)
        media_type = _sniff_or_reject(data, FAVICON_MEDIA_TYPES, kind=kind)

    row = await _own_row(session, tenant.id)
    if row is None:
        # update-or-insert, а не add: вторая строка сделала бы ответ ручки
        # неопределённым (грабля BIZ-61 срез-2).
        row = TenantBranding(tenant_id=tenant.id)
        session.add(row)
    if kind == "logo":
        row.logo_image = data
        row.logo_media_type = media_type
    else:
        row.favicon_image = data
        row.favicon_media_type = media_type
    await session.commit()


async def _drop_image(session: AsyncSession, tenant: Tenant, *, kind: str) -> None:
    """Убрать свою картинку — вернуться к наследованию, а не «стереть везде».

    Строка не удаляется: в ней могут жить имя и цвет. Чистятся ровно две
    колонки картинки.
    """

    row = await _own_row(session, tenant.id)
    if row is None:
        return
    if kind == "logo":
        row.logo_image = None
        row.logo_media_type = None
    else:
        row.favicon_image = None
        row.favicon_media_type = None
    await session.commit()


@router.put("/logo", response_model=TenantBrandingRead)
@audit_operation("update", "tenant_branding")
async def upload_logo(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    file: UploadFile = File(...),
) -> TenantBrandingRead:
    _require_brand_editor(credentials, tenant)
    await _store_image(session, tenant, file, kind="logo")
    return await read_own_branding(session, tenant, credentials)


@router.delete("/logo", response_model=TenantBrandingRead)
@audit_operation("update", "tenant_branding")
async def delete_logo(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantBrandingRead:
    _require_brand_editor(credentials, tenant)
    await _drop_image(session, tenant, kind="logo")
    return await read_own_branding(session, tenant, credentials)


@router.put("/favicon", response_model=TenantBrandingRead)
@audit_operation("update", "tenant_branding")
async def upload_favicon(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
    file: UploadFile = File(...),
) -> TenantBrandingRead:
    _require_brand_editor(credentials, tenant)
    await _store_image(session, tenant, file, kind="favicon")
    return await read_own_branding(session, tenant, credentials)


@router.delete("/favicon", response_model=TenantBrandingRead)
@audit_operation("update", "tenant_branding")
async def delete_favicon(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
) -> TenantBrandingRead:
    _require_brand_editor(credentials, tenant)
    await _drop_image(session, tenant, kind="favicon")
    return await read_own_branding(session, tenant, credentials)
