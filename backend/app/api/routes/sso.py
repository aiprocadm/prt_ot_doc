"""Единый вход через корпоративного провайдера (BIZ-53 разд. 53.3, срез-204).

Правила «пускать ли» — в ``app.domains.sso.rules`` (без сети и без базы).
Разговор с провайдером — в ``app.services.oidc_client``. Здесь только сшивка:
кто спрашивает, что лежит в базе и какие токены выдаём в конце.

## Решения, которые важнее кода

**Состояние входа — подписанный короткоживущий токен, а не строка в таблице.**
В него кладутся арендатор и ``nonce``, срок — пять минут. Таблица потребовала бы
уборки просроченных строк фоновой задачей, а такая задача однажды не проснётся
именно тогда, когда это опаснее всего (урок среза-10 про сессии работы «от
имени»). Цена решения названа честно: подписанное состояние можно ПОВТОРИТЬ в
пределах пяти минут; от повтора защищает то, что код обмена у провайдера
одноразовый, а ``nonce`` сверяется с токеном личности.

**Отказ всегда называет причину словами.** «Вход не настроен», «домен не
разрешён» и «вас нет в системе» чинят РАЗНЫЕ люди: администратор платформы,
администратор заказчика и кадровик. Общее «не удалось войти» отправляет всех
троих в поддержку.

**Проверка «настроено ли» отвечает одинаково для чужого и несуществующего
арендатора.** Иначе по этой ручке можно было бы перебирать список заказчиков.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from jose import JWTError, jwt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_session, get_tenant_record
from app.core.audit_decorator import audit_operation
from app.core.config import Settings, get_settings
from app.core.security import (
    AccessContext,
    abac,
    decode_token,
    issue_access_token,
    issue_refresh_token,
    rbac,
)
from app.core.tenant_validation import TenantContextValidator
from app.domains.sso.rules import (
    PROVIDER_DISABLED,
    PROVIDER_OIDC,
    SsoConfig,
    SsoRefused,
    decide_jit,
    ensure_usable,
    normalize_domains,
)
from app.models.models import RoleEnum, Tenant, User
from app.models.sso import TenantSsoConfig
from app.schemas.sso import SsoConfigRead, SsoConfigWrite, SsoStartResponse, SsoStatusResponse
from app.services.oidc_client import OidcError, authorization_url, exchange_code
from app.services.refresh_sessions import create_refresh_session

#: Вход — ПУБЛИЧНЫЙ роутер. У человека ещё нет токена, а браузер возвращается
#: от провайдера без наших заголовков: потребовать заголовок арендатора здесь
#: значило бы сделать вход невозможным. Арендатор приезжает слагом в адресе
#: (начало) и подписанным состоянием (возврат).
public_router = APIRouter(tags=["sso"])

#: Настройка — обычный арендаторский роутер: её правит вошедший администратор.
router = APIRouter(tags=["sso"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: Настраивает единый вход тот же круг, что управляет учётными записями.
_SSO_ADMIN_ROLES = ["admin", "owner"]

#: Пять минут: столько человек идёт к провайдеру и обратно. Дольше — окно для
#: повтора состояния, короче — отказ у того, кто вводил пароль медленно.
_STATE_TTL_SECONDS = 300


def _tenant_resource_id(tenant: Tenant = Depends(get_tenant_record)) -> Any:
    return getattr(tenant, "id", None)


def _to_rules(row: TenantSsoConfig | None) -> SsoConfig | None:
    if row is None:
        return None
    return SsoConfig(
        provider=row.provider,
        issuer=row.issuer,
        client_id=row.client_id,
        client_secret_env=row.client_secret_env,
        authorization_endpoint=row.authorization_endpoint,
        token_endpoint=row.token_endpoint,
        jwks_uri=row.jwks_uri,
        email_domains=normalize_domains(row.email_domains),
        jit_enabled=row.jit_enabled,
        default_role=row.default_role,
    )


async def _config_for_tenant(session: AsyncSession, tenant_id: str) -> TenantSsoConfig | None:
    return await session.scalar(
        select(TenantSsoConfig).where(TenantSsoConfig.tenant_id == tenant_id)
    )


def _client_secret(config: SsoConfig, settings: Settings) -> str | None:
    """Секрет берётся из ОКРУЖЕНИЯ по имени из настройки, а не из базы."""

    import os  # noqa: PLC0415 - читаем окружение в момент входа, а не на импорте

    name = (config.client_secret_env or "").strip()
    if not name:
        return None
    _ = settings
    return os.environ.get(name) or None


def _encode_state(*, tenant_slug: str, nonce: str, settings: Settings) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": "sso-login",
        "tenant": tenant_slug,
        "nonce": nonce,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=_STATE_TTL_SECONDS)).timestamp()),
        "typ": "sso_state",
    }
    return jwt.encode(payload, settings.jwt_private_key_pem, algorithm=settings.jwt_algorithm)


def _decode_state(state: str, settings: Settings) -> dict[str, Any]:
    try:
        claims = jwt.decode(
            state,
            settings.jwt_public_key_pem,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка входа недействительна") from exc
    if claims.get("typ") != "sso_state":
        # Иначе сюда подошёл бы ЛЮБОЙ наш токен — например, чужой access.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка входа недействительна")
    return claims


@public_router.get("/auth/sso/{tenant_slug}/status", response_model=SsoStatusResponse)
async def sso_status(tenant_slug: str, session: SessionDep) -> SsoStatusResponse:
    """Показывать ли кнопку «Войти через SSO». Ответ одинаков для чужого и
    несуществующего арендатора — иначе по ручке перебирали бы заказчиков."""

    tenant = await session.scalar(
        select(Tenant).where(func.lower(Tenant.slug) == tenant_slug.strip().lower())
    )
    if tenant is None or not tenant.is_active:
        return SsoStatusResponse(enabled=False)
    config = _to_rules(await _config_for_tenant(session, str(tenant.id)))
    return SsoStatusResponse(enabled=bool(config and config.provider == PROVIDER_OIDC))


@public_router.get("/auth/sso/{tenant_slug}/start", response_model=SsoStartResponse)
async def sso_start(tenant_slug: str, session: SessionDep) -> SsoStartResponse:
    """Куда уводить человека к его провайдеру.

    Проверка настройки стоит ДО редиректа: увести на чужой сайт и вернуть с
    ошибкой — худший способ сказать «у вас не настроено».
    """

    settings = get_settings()
    tenant = await session.scalar(
        select(Tenant).where(func.lower(Tenant.slug) == tenant_slug.strip().lower())
    )
    if tenant is None or not tenant.is_active:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Единый вход для этой организации не настроен"
        )
    config = _to_rules(await _config_for_tenant(session, str(tenant.id)))
    try:
        usable = ensure_usable(config, secret=_client_secret(config or SsoConfig(), settings))
    except SsoRefused as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.title) from exc
    redirect_uri = (settings.sso_redirect_uri or "").strip()
    if not redirect_uri:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Адрес возврата единого входа не задан в окружении (SSO_REDIRECT_URI)",
        )
    nonce = uuid4().hex
    state = _encode_state(tenant_slug=tenant.slug, nonce=nonce, settings=settings)
    return SsoStartResponse(
        authorization_url=authorization_url(
            usable, redirect_uri=redirect_uri, state=state, nonce=nonce
        )
    )


def _http_client() -> httpx.AsyncClient:
    """Отдельная функция — чтобы тест подменил транспорт, не трогая маршрут."""

    return httpx.AsyncClient(timeout=15.0)


@public_router.get("/auth/sso/callback")
@audit_operation("login", "auth_session")
async def sso_callback(
    session: SessionDep,
    response: Response,
    code: str = Query(description="Одноразовый код от провайдера"),
    state: str = Query(description="Состояние, выданное при начале входа"),
) -> dict:
    """Возврат от провайдера: проверить, при необходимости завести, впустить."""

    settings = get_settings()
    claims = _decode_state(state, settings)
    tenant_slug = str(claims.get("tenant") or "")
    nonce = str(claims.get("nonce") or "")
    tenant = await session.scalar(
        select(Tenant).where(func.lower(Tenant.slug) == tenant_slug.lower())
    )
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Ссылка входа недействительна")

    config = _to_rules(await _config_for_tenant(session, str(tenant.id)))
    secret = _client_secret(config or SsoConfig(), settings)
    try:
        usable = ensure_usable(config, secret=secret)
    except SsoRefused as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, exc.title) from exc

    redirect_uri = (settings.sso_redirect_uri or "").strip()
    client = _http_client()
    try:
        identity = await exchange_code(
            usable,
            code=code,
            redirect_uri=redirect_uri,
            nonce=nonce,
            client_secret=secret or "",
            client=client,
        )
    except OidcError as exc:
        # Наружу — одна фраза: подробности разговора с провайдером могут
        # содержать то, что мы ему только что отправили.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Вход через SSO не удался") from exc
    finally:
        await client.aclose()

    existing = None
    if identity.email:
        existing = await session.scalar(
            select(User)
            .options(selectinload(User.roles))
            .where(
                func.lower(User.email) == identity.email.strip().lower(),
                User.tenant_id == str(tenant.id),
            )
        )
    try:
        decision = decide_jit(
            usable,
            email=identity.email,
            email_verified=identity.email_verified,
            existing_user_active=None if existing is None else bool(existing.is_active),
        )
    except SsoRefused as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, exc.title) from exc

    user = existing
    if decision.create:
        user = User(
            tenant_id=str(tenant.id),
            email=decision.email,
            full_name=identity.full_name or decision.email,
            # Пароля у такого сотрудника нет и быть не должно: вход только через
            # провайдера. Пустая строка не подойдёт ни одному проверяющему хэшу,
            # и это ровно то, что нужно, — локальный вход невозможен.
            hashed_password="",
            role=RoleEnum(decision.role),
            is_active=True,
        )
        session.add(user)
        await session.flush()
    assert user is not None

    await session.execute(
        update(User).where(User.id == user.id).values(last_login_at=datetime.now(timezone.utc))
    )
    role_values = sorted(
        {user.role.value, *(r.role.value for r in getattr(user, "roles", []) if r)}
    )
    additional_claims: dict[str, Any] = {"tenant_id": user.tenant_id, "roles": role_values}
    if user.company_id:
        additional_claims["company_id"] = str(user.company_id)
    access_token = issue_access_token(
        subject=user.id,
        tenant=tenant.slug,
        role=user.role.value,
        additional_claims=additional_claims,
    )
    refresh_token = issue_refresh_token(
        subject=user.id,
        tenant=tenant.slug,
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
    _ = response
    return {"access_token": access_token, "token_type": "bearer", "created": decision.create}


@router.get("/settings/sso", response_model=SsoConfigRead)
async def read_sso_config(
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access: AccessContext = Depends(rbac(_SSO_ADMIN_ROLES)),
) -> SsoConfigRead:
    """Настройка своего арендатора. Секрета здесь нет — только имя переменной."""

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    row = await _config_for_tenant(session, str(tenant.id))
    if row is None:
        return SsoConfigRead(provider=PROVIDER_DISABLED)
    return SsoConfigRead(
        provider=row.provider,
        issuer=row.issuer,
        client_id=row.client_id,
        client_secret_env=row.client_secret_env,
        authorization_endpoint=row.authorization_endpoint,
        token_endpoint=row.token_endpoint,
        jwks_uri=row.jwks_uri,
        email_domains=list(normalize_domains(row.email_domains)),
        jit_enabled=row.jit_enabled,
        default_role=row.default_role,
        secret_present=bool(_client_secret(_to_rules(row) or SsoConfig(), get_settings())),
    )


@router.put("/settings/sso", response_model=SsoConfigRead)
@audit_operation("update", "tenant_sso_config")
async def write_sso_config(
    payload: SsoConfigWrite,
    session: SessionDep,
    tenant: Tenant = Depends(get_tenant_record),
    access=Depends(
        abac(_tenant_resource_id, required_roles=_SSO_ADMIN_ROLES, action="configure sso")
    ),
) -> SsoConfigRead:
    """Завести или изменить настройку единого входа."""

    TenantContextValidator.ensure_tenant_context(tenant)
    _ = access
    row = await _config_for_tenant(session, str(tenant.id))
    if row is None:
        row = TenantSsoConfig(tenant_id=str(tenant.id))
        session.add(row)
    row.provider = payload.provider
    row.issuer = payload.issuer
    row.client_id = payload.client_id
    row.client_secret_env = payload.client_secret_env
    row.authorization_endpoint = payload.authorization_endpoint
    row.token_endpoint = payload.token_endpoint
    row.jwks_uri = payload.jwks_uri
    row.email_domains = list(normalize_domains(payload.email_domains))
    row.jit_enabled = payload.jit_enabled
    row.default_role = payload.default_role
    await session.commit()
    return await read_sso_config(session=session, tenant=tenant, access=None)  # type: ignore[arg-type]
