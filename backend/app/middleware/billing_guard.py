from __future__ import annotations

from app.api.dependencies import _resolve_tenant_slug
from app.db.session import AsyncSessionLocal
from app.models.models import Tenant
from app.services.billing import BillingService
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class BillingGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if not path.startswith("/api/v1") or path.startswith("/api/v1/auth") or path.startswith("/api/v1/billing"):
            return await call_next(request)
        tenant_slug = _resolve_tenant_slug(request)
        if not tenant_slug:
            return await call_next(request)

        action = None
        if request.method == "POST" and path.endswith("/documents/generate"):
            action = "documents.generate"
        elif request.method == "POST" and "/edo" in path and ":send" in path:
            action = "edo.send"

        async with AsyncSessionLocal(tenant="public", include_public=False, create_schema=False) as session:
            from sqlalchemy import select
            tenant = (await session.execute(select(Tenant).where(Tenant.slug == tenant_slug))).scalars().first()
            if tenant is None:
                return await call_next(request)
            service = BillingService(session)
            await service.assert_allowed(tenant, action or "request")

        return await call_next(request)
