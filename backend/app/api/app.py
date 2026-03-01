"""Application factory and API wiring."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.error_handlers import register_exception_handlers
from app.api.routes import health, ws_stub
from app.api.v1.router import router as v1_router
from app.core.config import Settings, SettingsError, bootstrap
from app.core.idempotency import idempotency_dependency, store_idempotent_response
from app.core.metrics import render_metrics
from app.core.rate_limit import (
    RateLimitExceeded,
    SlowAPIMiddleware,
    _rate_limit_exceeded_handler,
    configure_rate_limiter,
    limiter,
)
from app.domains.files import s3
from app.db.session import dispose_engine
from app.services.dev_bootstrap import bootstrap_admin_user
from app.services.demo_bootstrap import bootstrap_demo_tenant
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.tenant import TenantMiddleware
from app.middleware.billing_guard import BillingGuardMiddleware

__all__ = ["create_app", "SettingsError"]


def _normalize_patterns(values: Iterable[str]) -> list[str]:
    patterns = [value for value in (value.strip() for value in values) if value]
    return ["*"] if "*" in patterns else patterns


def _configure_middlewares(app: FastAPI, settings: Settings) -> None:
    allowed_hosts = _normalize_patterns(settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    allow_origins = _normalize_patterns(settings.allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(TenantMiddleware, metrics_enabled=settings.enable_metrics)
    app.add_middleware(BillingGuardMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(ObservabilityMiddleware, settings=settings)


def _create_lifespan(settings: Settings) -> Callable[[FastAPI], AsyncIterator[None]]:
    logger = logging.getLogger("app.lifecycle")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("app.startup", extra={"env": settings.app_env})
        logger.info(
            "app.startup.mode",
            extra={
                "run_mode": settings.app_run_mode,
                "storage_backend": settings.s3_backend,
                "storage_root": str(settings.storage_root_path)
                if settings.s3_backend == "local"
                else None,
                "celery_eager": settings.celery_eager,
                "redis_enabled": settings.redis_enabled,
                "settings": settings.redacted(),
            },
        )
        try:
            s3.ensure_bucket()
            await bootstrap_admin_user(settings)
            await bootstrap_demo_tenant(settings)
        except Exception:  # pragma: no cover - infrastructure guard
            logger.exception("app.startup.s3-bucket-init-failed")
            raise

        try:
            yield
        finally:
            logger.info("app.shutdown")
            try:
                await dispose_engine()
            except Exception:  # pragma: no cover - defensive shutdown
                logger.exception("app.shutdown.db-dispose-failed")

    return lifespan


def _register_metrics_endpoint(app: FastAPI, settings: Settings) -> None:
    if not settings.enable_metrics:
        return

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        redis_client = getattr(app.state, "redis_client", None)
        payload, content_type = await render_metrics(
            settings=settings,
            redis_client=redis_client,
        )
        return Response(content=payload, media_type=content_type)

def _register_idempotency_middleware(app: FastAPI) -> None:
    logger = logging.getLogger("app.idempotency")

    @app.middleware("http")
    async def _idempotency(request: Request, call_next):  # type: ignore[override]
        precomputed = await idempotency_dependency(request)
        if precomputed is not None:
            return precomputed

        response = await call_next(request)
        try:
            if getattr(response, "media_type", None) == "application/json":
                await store_idempotent_response(request, response)
        except Exception:  # pragma: no cover - defensive logging
            logger.debug("app.idempotency.store_failed", exc_info=True)
        return response



def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a FastAPI application instance."""

    settings = settings or bootstrap("api")

    app = FastAPI(
        title=settings.app_name,
        debug=False,
        docs_url=f"{settings.api_prefix}/docs",
        openapi_url=f"{settings.api_prefix}/openapi.json",
        lifespan=_create_lifespan(settings),
    )

    app.state.debug = settings.debug
    app.state.settings = settings

    _configure_middlewares(app, settings)
    configure_rate_limiter(settings)
    if hasattr(limiter, "reset"):
        limiter.reset()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(health.router)
    app.include_router(ws_stub.router)
    _register_metrics_endpoint(app, settings)
    _register_idempotency_middleware(app)

    app.include_router(v1_router, prefix=settings.api_v1_prefix)

    register_exception_handlers(app)

    return app


app = create_app()
