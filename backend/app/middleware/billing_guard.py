from __future__ import annotations

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.dependencies import _fetch_tenant_by_identifier, _resolve_tenant_slug
from app.db.session import AsyncSessionLocal
from app.services.billing import BillingService


def resolve_billing_action(request: Request) -> str:
    path = request.url.path
    method = request.method.upper()

    if method == "POST" and (
        path.endswith("/documents/generate") or path.endswith("/documents:generate")
    ):
        return "documents.generate"
    if method == "POST" and (
        path.endswith("/edo/send")
        or path.endswith("/edo:send")
        or ("/edo" in path and ":send" in path)
    ):
        return "edo.send"
    if method == "POST" and (
        path.endswith("/files:upload-session") or path.endswith(":upload-session")
    ):
        return "files.upload"
    if method == "POST" and (path.endswith("/templates") or path.endswith("/templates/")):
        return "templates.create"
    if method == "POST" and (path.endswith("/persons") or path.endswith("/persons/")):
        return "persons.create"
    if method == "POST" and (path.endswith("/contractors") or path.endswith("/contractors/")):
        return "contractors.create"
    return "request"


class BillingGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if (
            not path.startswith("/api/v1")
            or path.startswith("/api/v1/auth")
            or path.startswith("/api/v1/billing")
        ):
            return await call_next(request)
        tenant_identifier = _resolve_tenant_slug(request)
        if not tenant_identifier:
            return await call_next(request)

        # В ``X-Tenant`` приходит не только slug: у клиентов и тестов там бывает
        # UUID или код арендатора. Прежний поиск «только по Tenant.slug» в этом
        # случае НЕ НАХОДИЛ арендатора и молча пропускал запрос — биллинг-гейт
        # переставал работать ровно там, где заголовок отличался от slug'а
        # (fail-open: отказ защиты, выглядящий как разрешение). Найдено в волне
        # OPS-72 и закрыто здесь тем же общим резолвером, что и везде.
        try:
            tenant = await _fetch_tenant_by_identifier(tenant_identifier)
        except HTTPException:
            # Неизвестный или неактивный арендатор — забота обычного обработчика
            # (404/403), а не биллинга.
            return await call_next(request)

        action = resolve_billing_action(request)

        # Session pinned to the request tenant (slug → UUID resolved on enter), so
        # the SEC-65 RLS GUC matches the subscriptions/usage/override rows the
        # billing gate reads and the usage row it flushes. A tenant-less session
        # would see nothing under FORCE RLS (fail-open gate / rejected INSERT).
        # Сессия пиннится на РАЗРЕШЁННЫЙ slug, а не на содержимое заголовка:
        # с UUID в ``tenant=`` search_path указывал бы на несуществующую схему.
        async with AsyncSessionLocal(
            tenant=tenant.slug, include_public=False, create_schema=False
        ) as session:
            service = BillingService(session)
            await service.assert_allowed(tenant, action)

        return await call_next(request)
