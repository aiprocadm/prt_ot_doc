from __future__ import annotations

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.dependencies import _resolve_tenant_slug
from app.db.session import AsyncSessionLocal
from app.models.models import Tenant
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
        tenant_slug = _resolve_tenant_slug(request)
        if not tenant_slug:
            return await call_next(request)

        action = resolve_billing_action(request)

        # Session pinned to the request tenant (slug → UUID resolved on enter), so
        # the SEC-65 RLS GUC matches the subscriptions/usage/override rows the
        # billing gate reads and the usage row it flushes. A tenant-less session
        # would see nothing under FORCE RLS (fail-open gate / rejected INSERT).
        async with AsyncSessionLocal(
            tenant=tenant_slug, include_public=False, create_schema=False
        ) as session:
            from sqlalchemy import select

            tenant = (
                (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug)))
                .scalars()
                .first()
            )
            if tenant is None:
                return await call_next(request)
            service = BillingService(session)
            await service.assert_allowed(tenant, action)

        return await call_next(request)
