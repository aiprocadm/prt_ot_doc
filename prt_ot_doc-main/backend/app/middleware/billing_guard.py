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

    if method == "POST" and (path.endswith("/documents/generate") or path.endswith("/documents:generate")):
        return "documents.generate"
    if method == "POST" and (path.endswith("/edo/send") or path.endswith("/edo:send") or ("/edo" in path and ":send" in path)):
        return "edo.send"
    if method == "POST" and (path.endswith("/files:upload-session") or path.endswith(":upload-session")):
        return "files.upload"
    if method == "POST" and (path.endswith("/templates") or path.endswith("/templates/")):
        return "templates.create"
    if method == "POST" and (path.endswith("/persons") or path.endswith("/persons/")):
        return "users.create"
    if method == "POST" and (path.endswith("/contractors") or path.endswith("/contractors/")):
        return "contractors.create"
    return "request"


class BillingGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1") or path.startswith("/api/v1/auth") or path.startswith("/api/v1/billing"):
            return await call_next(request)
        tenant_slug = _resolve_tenant_slug(request)
        if not tenant_slug:
            return await call_next(request)

        action = None
        if request.method == "POST" and (path.endswith("/documents/generate") or path.endswith("/documents:generate")):
            action = "documents.generate"
        elif request.method == "POST" and (path.endswith("/edo/send") or path.endswith("/edo:send") or ("/edo" in path and ":send" in path)):
            action = "edo.send"
        elif request.method == "POST" and (path.endswith("/files:upload-session") or path.endswith(":upload-session")):
            action = "files.upload"
        action = resolve_billing_action(request)

        async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
            from sqlalchemy import select
            tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalars().first()
            if tenant is None:
                return await call_next(request)
            service = BillingService(session)
            await service.assert_allowed(tenant, action)

        return await call_next(request)
