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
from app.db.rls_runtime import UnsafeDatabaseRoleError, verify_runtime_role
from app.db.session import aensure_shared_schema, dispose_engine
from app.middleware.api_deprecation import ApiDeprecationMiddleware
from app.middleware.billing_guard import BillingGuardMiddleware
from app.middleware.global_error_handler import GlobalErrorHandlerMiddleware
from app.middleware.impersonation_guard import ImpersonationGuardMiddleware
from app.middleware.observability import ObservabilityMiddleware
from app.middleware.offboarding_readonly import OffboardingReadOnlyMiddleware
from app.middleware.reseller_suspension import ResellerSuspensionReadOnlyMiddleware
from app.middleware.security_headers import DEFAULT_API_CSP, SecurityHeadersMiddleware
from app.middleware.tenant import TenantMiddleware
from app.modules.files import s3
from app.services.demo_bootstrap import bootstrap_demo_tenant
from app.services.dev_bootstrap import bootstrap_admin_user

__all__ = ["create_app", "SettingsError"]

_CORS_ALLOW_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
_CORS_ALLOW_HEADERS = (
    "Accept",
    "Accept-Language",
    "Authorization",
    "Cache-Control",
    "Content-Type",
    "Idempotency-Key",
    "If-Match",
    "If-None-Match",
    "X-Actor-Id",
    "X-Attributes",
    "X-Correlation-Id",
    "X-Inbound-Webhook-Signature",
    "X-Replace-Options",
    "X-Request-Id",
    "X-Roles",
    "X-Signature",
    "X-Tenant",
    "X-Tenant-Code",
    "X-Tenant-Slug",
    "X-Trace-Id",
    "X-User-Id",
    "X-Webhook-Signature",
)


def _normalize_patterns(values: Iterable[str]) -> list[str]:
    patterns = [value for value in (value.strip() for value in values) if value]
    return ["*"] if "*" in patterns else patterns


def _docs_path_prefixes(settings: Settings) -> tuple[str, ...]:
    """Пути документации, исключённые из CSP: Swagger UI тянет ассеты с CDN.

    В production документация отключена (`_disable_openapi_in_production`), поэтому
    исключение не расширяет поверхность атаки.
    """

    prefix = settings.api_prefix.rstrip("/")
    return (f"{prefix}/docs", f"{prefix}/redoc")


def _configure_middlewares(app: FastAPI, settings: Settings) -> None:
    # Global error handler must be first to catch all exceptions
    app.add_middleware(GlobalErrorHandlerMiddleware)

    allowed_hosts = _normalize_patterns(settings.allowed_hosts)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

    allow_origins = _normalize_patterns(settings.allowed_origins)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=list(_CORS_ALLOW_METHODS),
        allow_headers=list(_CORS_ALLOW_HEADERS),
    )
    app.add_middleware(TenantMiddleware, metrics_enabled=settings.enable_metrics)
    app.add_middleware(BillingGuardMiddleware)
    # BIZ-52 срез-3 (разд. 52.1): приостановлен партнёр — его клиенты только на
    # чтение. Стоит ПЕРЕД биллинг-гейтом (добавлено раньше = выполняется позже):
    # клиенту, чей партнёр приостановлен, ответ «оплатите подписку» вводит в
    # заблуждение — должен не он, и заплатить за партнёра он не может.
    app.add_middleware(ResellerSuspensionReadOnlyMiddleware)
    # OPS-72: grace-период офбординга — данные только на чтение. Starlette
    # выполняет middleware в ОБРАТНОМ порядке добавления, поэтому строка ниже
    # ставит проверку ПЕРЕД биллинг-гейтом сознательно: расторгающемуся
    # арендатору честнее ответить «идёт расторжение, данные только на чтение»,
    # чем «оплатите подписку» — платить он как раз и не собирается.
    app.add_middleware(OffboardingReadOnlyMiddleware)
    # BIZ-49 срез-10: запреты для работы «от имени клиента» (Доп. №3 63.2).
    # Добавлен после офбординга, то есть выполняется ПЕРЕД ним: специалисту,
    # который пытается удалить данные из чужого контекста, надо ответить
    # именно про контекст, а не про состояние подписки арендатора.
    app.add_middleware(ImpersonationGuardMiddleware)
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
                "storage_root": (
                    str(settings.storage_root_path) if settings.s3_backend == "local" else None
                ),
                "celery_eager": settings.celery_eager,
                "redis_enabled": settings.redis_enabled,
                "settings": settings.redacted(),
            },
        )
        # SEC-65: row-level policies are inert for a SUPERUSER/BYPASSRLS role, so
        # refuse to serve on a misprovisioned deployment (staging/production) and
        # warn loudly everywhere else. Own block: a failure here is a security
        # misconfiguration, not an infrastructure hiccup.
        from app.db.session import engine as _engine

        try:
            async with _engine.connect() as conn:
                await verify_runtime_role(
                    conn,
                    enforce=settings.rls_enforce_unprivileged_db_role,
                    component="api",
                )
        except UnsafeDatabaseRoleError:
            logger.exception("app.startup.unsafe-db-role")
            raise
        except Exception:  # pragma: no cover - probe must never mask a real startup
            logger.warning("app.startup.db-role-probe-failed", exc_info=True)

        try:
            # Register cross-base FK resolution so that string-form
            # ForeignKey("tenant.id") on TenantBaseModel subclasses can resolve
            # at flush time. Safe to call multiple times; must run before the
            # first session.flush (bootstrap_demo_tenant below is the first
            # flush in the lifespan).
            from app.db.session import register_cross_base_fk_resolution

            register_cross_base_fk_resolution()
            s3.ensure_bucket()
            # iter-22: provision the shared schema on this loop BEFORE any
            # session_scope / AsyncSessionLocal call. Without this, the first
            # implicit ensure_shared_schema(implicit=True) from AsyncSessionLocal
            # spawns a worker thread + asyncio.run, which seeds the engine's
            # connection pool with futures bound to that worker loop. When the
            # worker thread exits and the next access comes from the lifespan
            # loop, asyncpg raises "Future attached to a different loop" and
            # bootstrap_demo_tenant fails at _create_tenant_schema.
            await aensure_shared_schema()
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

    # Приложение и настройки берём из запроса, а НЕ из замыкания. FastAPI 0.141
    # кэширует признаки обработчика в вечном lru_cache, ключ которого — сама
    # функция; замкни она на себя `app`, и приложение уже не освободится никогда.
    # В проде это незаметно (приложение одно), а в тестах `app_fixture` создаёт
    # его на каждый тест — прогон удерживал их все и съедал память гигабайтами.
    # Сторож — tests/test_app_memory.py.
    @app.get("/metrics", include_in_schema=False)
    async def metrics(request: Request) -> Response:
        payload, content_type = await render_metrics(
            settings=request.app.state.settings,
            redis_client=getattr(request.app.state, "redis_client", None),
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

    api_prefix = settings.api_prefix.rstrip("/") or ""
    if settings.enable_openapi_docs:
        docs_url = f"{api_prefix}/docs"
        openapi_url = f"{api_prefix}/openapi.json"
        redoc_url = f"{api_prefix}/redoc"
    else:
        docs_url = None
        openapi_url = None
        redoc_url = None

    app = FastAPI(
        title=settings.app_name,
        debug=False,
        docs_url=docs_url,
        openapi_url=openapi_url,
        redoc_url=redoc_url,
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

    # OPS-73 (разд. 73.2). Регистрируется здесь же, во внешнем поясе: заголовки
    # Deprecation/Sunset обязаны стоять и на ответах ошибок устаревшей ручки —
    # интеграция, получающая от неё только 4xx, всё равно должна узнать об
    # устаревании. Реестр поверхностей — core/api_deprecation.py (данные, не код).
    app.add_middleware(ApiDeprecationMiddleware)

    # SEC-64 (разд. 64.1). Регистрируется САМЫМ ПОСЛЕДНИМ — после обработчиков
    # ошибок и idempotency-слоя: добавленный позже оборачивает добавленных раньше.
    # Это не косметика: ответы «X-Tenant header required» и прочие ошибки собирает
    # внешний обработчик ошибок, и слой, стоящий внутри него, таких ответов не
    # видит вовсе — заголовки на них не попадали. Поймано тестом на ответах,
    # сформированных не обработчиком маршрута.
    if settings.security_headers_enabled:
        app.add_middleware(
            SecurityHeadersMiddleware,
            csp=settings.security_csp or DEFAULT_API_CSP,
            hsts_max_age=(
                settings.security_hsts_max_age
                if settings.app_env in ("production", "staging")
                else 0
            ),
            exempt_path_prefixes=_docs_path_prefixes(settings),
        )

    return app
