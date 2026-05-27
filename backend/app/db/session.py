"""Async database session management with tenant schema support."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import MetaData, Table, event, or_, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.tenant import get_current_tenant, tenant_schema
from app.modules.tenancy.context import get_tenant_context

_logger = logging.getLogger(__name__)

_settings = get_settings()
_DEFAULT_TENANT_SLUG = _settings.default_tenant_slug
_SHARED_SCHEMA = _settings.shared_schema


class TenantAsyncSession(AsyncSession):
    """Async session that applies the tenant search path on entry."""

    async def __aenter__(self) -> TenantAsyncSession:  # type: ignore[override]
        await super().__aenter__()
        await _hydrate_async_session_tenant_identity(self)
        await _apply_search_path(self)
        return self


class TenantBase(DeclarativeBase):
    """Declarative base for tenant-specific tables."""

    metadata = MetaData()


class SharedBase(DeclarativeBase):
    """Declarative base for tables shared across tenants."""

    metadata = MetaData(schema=_SHARED_SCHEMA)


engine: AsyncEngine
_session_factory: async_sessionmaker[TenantAsyncSession]
_SUPPORTS_SCHEMAS: bool
_SEARCH_PATH_SUPPORTED: bool
_DEFAULT_SCHEMA_NAME: str = "public"


def _initialize_engine(url: str, *, echo: bool) -> None:
    global engine, _session_factory, _SUPPORTS_SCHEMAS, _SEARCH_PATH_SUPPORTED, _DEFAULT_SCHEMA_NAME
    engine = create_async_engine(
        url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
    )
    _SUPPORTS_SCHEMAS = engine.dialect.name == "postgresql"
    _SEARCH_PATH_SUPPORTED = _SUPPORTS_SCHEMAS and engine.dialect.name == "postgresql"
    target_schema = _SHARED_SCHEMA if _SUPPORTS_SCHEMAS else None
    SharedBase.metadata.schema = target_schema
    for table in SharedBase.metadata.tables.values():
        table.schema = target_schema
    _session_factory = async_sessionmaker(
        engine,
        class_=TenantAsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


_initialize_engine(_settings.database_url, echo=_settings.database_echo)

_schema_lock = threading.RLock()
_shared_initialized = False
_tenant_initialized: set[str] = set()


def _normalize_tenant_id(value: object) -> str | None:
    if value is None:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        return str(UUID(candidate))
    except (TypeError, ValueError):
        return None


def _resolve_session_tenant_identity(session) -> tuple[str | None, str | None, str | None]:
    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return None, None, None

    tenant_id = _normalize_tenant_id(info.get("tenant_id"))
    tenant_slug = str(info.get("tenant_slug") or info.get("tenant") or "").strip().lower() or None
    tenant_schema = str(info.get("tenant_schema") or "").strip() or None

    if tenant_id is not None:
        info["tenant_id"] = tenant_id
        if tenant_slug:
            info.setdefault("tenant_slug", tenant_slug)
        if tenant_schema:
            info.setdefault("tenant_schema", tenant_schema)
        return tenant_id, tenant_slug, tenant_schema

    if not tenant_slug:
        legacy_identifier = _normalize_tenant_id(info.get("tenant"))
        if legacy_identifier is not None:
            info["tenant_id"] = legacy_identifier
            return legacy_identifier, None, tenant_schema
        return None, None, tenant_schema

    try:
        from app.models.models import Tenant
    except Exception:
        return None, tenant_slug, tenant_schema

    row = session.connection().execute(
        select(Tenant.id, Tenant.slug, Tenant.schema_name).where(
            or_(Tenant.slug == tenant_slug, Tenant.code == tenant_slug)
        )
    ).first()
    if row is None:
        return None, tenant_slug, tenant_schema

    tenant_id = str(row.id)
    resolved_slug = str(row.slug).strip().lower()
    resolved_schema = str(row.schema_name or tenant_schema or "").strip() or None
    info["tenant_id"] = tenant_id
    info["tenant_slug"] = resolved_slug
    if resolved_schema:
        info["tenant_schema"] = resolved_schema
    return tenant_id, resolved_slug, resolved_schema


async def _hydrate_async_session_tenant_identity(
    session: AsyncSession,
) -> tuple[str | None, str | None, str | None]:
    try:
        from app.models.models import Tenant
    except Exception:
        return None, None, None

    info = getattr(session, "info", None)
    if not isinstance(info, dict):
        return None, None, None

    tenant_id = _normalize_tenant_id(info.get("tenant_id"))
    tenant_slug = str(info.get("tenant_slug") or info.get("tenant") or "").strip().lower() or None
    tenant_schema_name = str(info.get("tenant_schema") or "").strip() or None

    if tenant_id and tenant_slug and tenant_schema_name:
        info["tenant_id"] = tenant_id
        info["tenant_slug"] = tenant_slug
        info["tenant_schema"] = tenant_schema_name
        info["tenant"] = tenant_slug
        return tenant_id, tenant_slug, tenant_schema_name

    filters = []
    if tenant_id:
        filters.append(Tenant.id == tenant_id)
    if tenant_slug:
        filters.extend((Tenant.slug == tenant_slug, Tenant.code == tenant_slug))
    if not filters:
        return tenant_id, tenant_slug, tenant_schema_name

    try:
        row = (
            await session.execute(
                select(Tenant.id, Tenant.slug, Tenant.schema_name).where(or_(*filters)).limit(1)
            )
        ).first()
    except Exception:
        # If the hydration query failed (e.g. minimal/restored DB lacks
        # Tenant.schema_name column, or table is missing), we must roll back
        # so the session's transaction is not left in an aborted state.
        # Otherwise the very next statement (typically _apply_search_path's
        # ``SET LOCAL search_path``) fails with InFailedSQLTransactionError
        # and bubbles out of __aenter__, poisoning all downstream callers.
        try:
            await session.rollback()
        except Exception:
            pass
        return tenant_id, tenant_slug, tenant_schema_name

    if row is None:
        return tenant_id, tenant_slug, tenant_schema_name

    resolved_tenant_id = str(row.id)
    resolved_tenant_slug = str(row.slug).strip().lower()
    resolved_tenant_schema = str(row.schema_name or tenant_schema_name or tenant_schema(resolved_tenant_slug)).strip()
    info["tenant_id"] = resolved_tenant_id
    info["tenant_slug"] = resolved_tenant_slug
    info["tenant_schema"] = resolved_tenant_schema
    info["tenant"] = resolved_tenant_slug
    return resolved_tenant_id, resolved_tenant_slug, resolved_tenant_schema


def _apply_default_tenant(session, flush_context, instances) -> None:
    """Populate ``tenant_id`` on new tenant-scoped models if missing."""

    tenant_id, tenant_slug, _tenant_schema = _resolve_session_tenant_identity(session)
    if not tenant_id:
        return

    for obj in session.new:
        if getattr(obj.__class__, "__tenant_model__", False):
            current = getattr(obj, "tenant_id", None)
            if current:
                if tenant_slug and str(current).strip().lower() == tenant_slug:
                    raise ValueError(
                        "Tenant-scoped model tenant_id must store tenant.id, not tenant.slug"
                    )
                continue
            setattr(obj, "tenant_id", tenant_id)


event.listen(TenantAsyncSession.sync_session_class, "before_flush", _apply_default_tenant)


def _run_in_thread(fn: Callable[[], None]) -> None:
    """Execute a callable in a temporary thread and wait for completion."""

    thread = threading.Thread(target=fn, daemon=True)
    thread.start()
    thread.join()


def _mirror_shared_tables_for_creation() -> list[Table]:
    """Temporarily mirror shared tables into tenant metadata for SQLite."""

    mirrored: list[Table] = []
    if _SUPPORTS_SCHEMAS:
        return mirrored

    for table in SharedBase.metadata.tables.values():
        key = table.key
        if key in TenantBase.metadata.tables:
            continue
        clone = table.to_metadata(TenantBase.metadata)
        mirrored.append(clone)
    return mirrored


def register_cross_base_fk_resolution() -> None:
    """Mirror shared tables into TenantBase.metadata for cross-base FK resolution.

    String-form ForeignKeys on TenantBaseModel subclasses (e.g. ``Company``'s
    ``tenant_id`` referring to ``ForeignKey("tenant.id")``) are resolved by
    SQLAlchemy at flush time by looking up the target name in the *source*
    mapper's MetaData under the unqualified key (the parent column's schema
    is ``None`` for TenantBase models). For SQLite the existing
    :func:`_mirror_shared_tables_for_creation` helper makes shared tables
    visible (and is undone after create_all); on Postgres the mirror is
    intentionally skipped — so the FK is unresolvable at flush time and ORM
    operations against tenant-scoped models raise
    ``sqlalchemy.exc.NoReferencedTableError``.

    Re-add the mirror permanently (idempotent) with ``schema=None`` so the
    mirrored copy is keyed by its bare table name (``"tenant"`` rather than
    ``"public.tenant"``) — that is the key SQLAlchemy's FK string resolver
    actually looks for. The original shared table keeps its real schema, so
    DDL for the shared schema is unaffected. Each mirrored table is tagged
    via ``info["cross_base_mirror"]`` so ``create_all`` against
    ``TenantBase.metadata`` can skip it (the real table lives in
    ``SharedBase.metadata``).

    Safe to call multiple times. Also wired to SQLAlchemy's ``after_configured``
    mapper event so it runs automatically before any flush, regardless of
    which entry point (CLI, lifespan, tests) is used.
    """

    for table in SharedBase.metadata.tables.values():
        if table.name in TenantBase.metadata.tables:
            continue
        mirrored = table.to_metadata(TenantBase.metadata, schema=None)
        mirrored.info["cross_base_mirror"] = True


def _tenant_tables_for_creation() -> list[Table]:
    """Return TenantBase tables that should participate in create_all.

    Excludes cross-base FK-resolution mirrors registered by
    :func:`register_cross_base_fk_resolution` — those exist only to satisfy
    SQLAlchemy's string FK resolver; the real shared tables are created via
    ``SharedBase.metadata.create_all``.
    """

    return [
        table
        for table in TenantBase.metadata.tables.values()
        if not table.info.get("cross_base_mirror")
    ]


# Run the registration automatically as soon as all SQLAlchemy mappers are
# configured — that is the natural "post-import, pre-flush" point. The
# explicit ``register_cross_base_fk_resolution()`` call kept in
# ``app/api/app.py::lifespan`` remains as a belt-and-suspenders safeguard
# for any flush that might happen before mapper auto-configure (e.g.
# Alembic offline mode or test fixtures that touch sessions directly).
from sqlalchemy.orm import Mapper as _Mapper  # noqa: E402  (intentional late import)


@event.listens_for(_Mapper, "after_configured")
def _auto_register_cross_base_fk_resolution() -> None:
    register_cross_base_fk_resolution()


async def _create_shared_schema() -> None:
    """Create database objects stored in the shared schema."""

    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        mirrored = _mirror_shared_tables_for_creation()

        try:
            if not _SUPPORTS_SCHEMAS:
                tables = _tenant_tables_for_creation()
                await conn.run_sync(
                    lambda sync_conn: TenantBase.metadata.create_all(
                        sync_conn, tables=tables
                    )
                )
        finally:
            for table in mirrored:
                TenantBase.metadata.remove(table)


async def _create_tenant_schema(schema: str) -> None:
    """Create database objects for an individual tenant schema."""

    if not _SUPPORTS_SCHEMAS:
        return
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        search_path_sql = f'SET LOCAL search_path TO "{schema}", "{_SHARED_SCHEMA}"'
        if _SEARCH_PATH_SUPPORTED:
            # iter-16f part 4 set this on the async conn, but FK to unqualified
            # ``tenant`` still failed in CI — the async→sync greenlet bridge
            # used by run_sync may not propagate session-scoped SET reliably.
            # Apply SET LOCAL on both sides of the bridge and verify.
            await conn.execute(text(search_path_sql))
            applied_async = (
                await conn.execute(text("SHOW search_path"))
            ).scalar_one()
            _logger.info(
                "tenant.schema.create.async.search_path",
                extra={"schema": schema, "search_path": applied_async},
            )
        tables = _tenant_tables_for_creation()

        def _create(sync_conn) -> None:
            if _SEARCH_PATH_SUPPORTED:
                sync_conn.execute(text(search_path_sql))
                applied_sync = sync_conn.execute(text("SHOW search_path")).scalar_one()
                _logger.info(
                    "tenant.schema.create.sync.search_path",
                    extra={"schema": schema, "search_path": applied_sync},
                )
            TenantBase.metadata.create_all(sync_conn, tables=tables)

        await conn.run_sync(_create)


def ensure_shared_schema(*, implicit: bool = False) -> None:
    """Ensure shared tables are present during local development.

    This is the **sync wrapper**. It uses ``_run_in_thread`` + ``asyncio.run``
    to bridge into an async context, which spawns a brand-new event loop and
    initialises the global ``engine``'s connection pool with connections
    bound to that worker loop. When the worker thread exits, those
    connections remain in the pool but their asyncpg futures are tied to a
    now-dead loop — and the next access from a *different* loop raises
    ``RuntimeError: Future ... attached to a different loop``. The exact
    failure surface that previously broke ``perf-smoke`` at
    ``_create_tenant_schema`` (see iter-22 PR fixing this).

    From an **async** context (FastAPI lifespan, async test fixtures), call
    :func:`aensure_shared_schema` FIRST — once it sets
    ``_shared_initialized = True`` the implicit sync call from
    :func:`AsyncSessionLocal` short-circuits and never spawns a worker loop.
    """

    global _shared_initialized
    if implicit and not _settings.runtime_schema_bootstrap:
        return
    if _settings.app_env == "production":
        return
    if _shared_initialized:
        return
    with _schema_lock:
        if _shared_initialized:
            return

        def runner() -> None:
            asyncio.run(_create_shared_schema())

        _run_in_thread(runner)
        _shared_initialized = True


async def aensure_shared_schema(*, implicit: bool = False) -> None:
    """Async-native :func:`ensure_shared_schema`.

    Call this from the FastAPI lifespan (or any other async startup path)
    BEFORE the first :func:`session_scope` / :func:`AsyncSessionLocal`. It
    runs ``_create_shared_schema`` directly on the current loop, then sets
    the same ``_shared_initialized`` flag the sync wrapper guards on — so
    later implicit sync calls from ``AsyncSessionLocal`` short-circuit and
    never spin up the worker-loop pattern that pollutes the engine pool
    (see :func:`ensure_shared_schema` docstring).
    """

    global _shared_initialized
    if implicit and not _settings.runtime_schema_bootstrap:
        return
    if _settings.app_env == "production":
        return
    if _shared_initialized:
        return
    await _create_shared_schema()
    _shared_initialized = True


def ensure_tenant_schema(
    slug: str,
    *,
    schema_name: str | None = None,
    implicit: bool = False,
) -> None:
    """Ensure tenant-specific tables exist for the provided tenant schema."""

    if implicit and not _settings.runtime_schema_bootstrap:
        return
    if not _SUPPORTS_SCHEMAS:
        return
    schema = str(schema_name or tenant_schema(slug)).strip()
    if not schema:
        return
    if _settings.app_env == "production":
        return
    if schema in _tenant_initialized:
        return
    with _schema_lock:
        if schema in _tenant_initialized:
            return

        def runner() -> None:
            asyncio.run(_create_tenant_schema(schema))

        _run_in_thread(runner)
        _tenant_initialized.add(schema)


async def aensure_tenant_schema(
    slug: str,
    *,
    schema_name: str | None = None,
    implicit: bool = False,
) -> None:
    """Async-native :func:`ensure_tenant_schema`.

    The sync wrapper does the heavy lifting via ``_run_in_thread`` +
    ``asyncio.run``, which spins up a brand-new event loop. The global
    async engine's connection pool was created in the calling loop, so any
    asyncpg connection it hands out has Futures bound to that loop —
    touching them from the worker loop raises ``RuntimeError: Future ...
    attached to a different loop`` and aborts ``CREATE TABLE`` mid-flight,
    leaving the tenant schema empty (and the next ``SELECT`` failing with
    ``UndefinedTableError``).

    From an async context (e.g. FastAPI lifespan), call this helper
    instead — it stays on the current loop, idempotent via the same
    ``_tenant_initialized`` cache.
    """

    if implicit and not _settings.runtime_schema_bootstrap:
        return
    if not _SUPPORTS_SCHEMAS:
        return
    schema = str(schema_name or tenant_schema(slug)).strip()
    if not schema:
        return
    if _settings.app_env == "production":
        return
    if schema in _tenant_initialized:
        return
    await _create_tenant_schema(schema)
    _tenant_initialized.add(schema)


def resolve_tenant_schema(tenant_id: str) -> str:
    """Build a deterministic per-tenant schema name from tenant UUID/string."""

    normalized = str(tenant_id).strip().lower().replace("-", "")
    return f"t_{normalized}"


def _format_search_path(schemas: Iterable[str]) -> str:
    """Return a comma-separated search path with quoted schema names."""

    normalized = []
    seen = set()
    for schema in schemas:
        if schema not in seen:
            seen.add(schema)
            normalized.append(f'"{schema}"')
    return ", ".join(normalized)


async def _apply_search_path(session: AsyncSession) -> None:
    """Set the session search path if tenant schemas are enabled."""

    if not _SUPPORTS_SCHEMAS:
        return
    search_path = session.info.get("search_path")
    if not search_path:
        return
    formatted = _format_search_path(search_path)
    if not _SEARCH_PATH_SUPPORTED:
        return
    await session.execute(text(f"SET LOCAL search_path TO {formatted}"))
    ctx = get_tenant_context()
    if ctx and ctx.correlation_id:
        safe = ctx.correlation_id.replace("\"", "")
        await session.execute(text(f"SET LOCAL application_name TO 'api:{safe}'"))


def AsyncSessionLocal(
    *,
    tenant: str | None = None,
    tenant_id: str | None = None,
    schema_name: str | None = None,
    include_public: bool = True,
    create_schema: bool = True,
) -> AsyncSession:
    """Build a tenant-aware session optionally creating schemas on demand."""

    ensure_shared_schema(implicit=True)
    slug = tenant or get_current_tenant().slug
    if _SUPPORTS_SCHEMAS:
        if schema_name:
            schema = schema_name
            slug = tenant or get_current_tenant().slug
            if create_schema and schema != _SHARED_SCHEMA:
                ensure_tenant_schema(slug, schema_name=schema, implicit=True)
        elif slug != _DEFAULT_TENANT_SLUG:
            if create_schema:
                ensure_tenant_schema(slug, implicit=True)
            schema = tenant_schema(slug)
        else:
            schema = _SHARED_SCHEMA
    else:
        schema = _SHARED_SCHEMA
    session = _session_factory()
    path: list[str] = [schema]
    if include_public and schema != _SHARED_SCHEMA:
        path.append(_SHARED_SCHEMA)
    session.info["search_path"] = path
    session.info["tenant"] = slug
    session.info["tenant_slug"] = slug
    session.info["tenant_schema"] = schema_name or schema
    normalized_tenant_id = _normalize_tenant_id(tenant_id)
    if normalized_tenant_id is not None:
        session.info["tenant_id"] = normalized_tenant_id
    elif tenant is not None:
        normalized_from_tenant = _normalize_tenant_id(tenant)
        if normalized_from_tenant is not None:
            session.info["tenant_id"] = normalized_from_tenant
    return session


@asynccontextmanager
async def session_scope(
    *, tenant: str | None = None, schema_name: str | None = None
) -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around operations executed per tenant.

    ``schema_name`` overrides the default-tenant → shared-schema short-circuit
    in :func:`AsyncSessionLocal`. Pass it when the tenant slug equals
    ``DEFAULT_TENANT_SLUG`` but the data actually lives in a tenant-specific
    schema (e.g. ``bootstrap_demo_tenant`` after ``aensure_tenant_schema``
    creates ``tenant_demo.*``).
    """

    async with AsyncSessionLocal(tenant=tenant, schema_name=schema_name) as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a tenant-aware session."""

    async with session_scope() as session:
        yield session


@asynccontextmanager
async def with_tenant_session(*, tenant_id: str, schema_name: str | None = None) -> AsyncIterator[AsyncSession]:
    """Compatibility helper that ensures tenant schema routing inside transaction scope."""

    schema = schema_name or resolve_tenant_schema(tenant_id)
    async with get_tenant_session(tenant_id=tenant_id, schema_name=schema) as session:
        yield session


SessionLocal = AsyncSessionLocal


@asynccontextmanager
async def get_tenant_session(
    *, tenant: str | None = None, tenant_id: str | None = None, schema_name: str | None = None
) -> AsyncIterator[AsyncSession]:
    """Return a tenant-bound session and enforce schema routing."""

    async with AsyncSessionLocal(tenant=tenant, tenant_id=tenant_id, schema_name=schema_name) as session:
        if _SEARCH_PATH_SUPPORTED:
            schema = schema_name or tenant_schema(tenant or tenant_id or _DEFAULT_TENANT_SLUG)
            try:
                await session.execute(text(f'SET LOCAL search_path TO "{schema}", "{_SHARED_SCHEMA}"'))
            except Exception:
                await session.execute(text(f'SET search_path TO "{schema}", "{_SHARED_SCHEMA}"'))
            ctx = get_tenant_context()
            if ctx and ctx.correlation_id:
                safe = ctx.correlation_id.replace("\"", "")
                await session.execute(text(f"SET LOCAL application_name TO 'api:{safe}'"))
        try:
            yield session
        finally:
            if _SEARCH_PATH_SUPPORTED:
                try:
                    await session.execute(text(f'SET search_path TO "{_SHARED_SCHEMA}"'))
                except Exception:
                    pass


def configure_engine(
    *, database_url: str | None = None, echo: bool | None = None
) -> None:
    """Reconfigure the global SQLAlchemy engine.

    Useful for tests that need to bind the ORM to an in-memory database.
    """

    settings = get_settings()
    global _settings, _DEFAULT_TENANT_SLUG, _SHARED_SCHEMA
    _settings = settings
    _DEFAULT_TENANT_SLUG = settings.default_tenant_slug
    _SHARED_SCHEMA = settings.shared_schema
    url = database_url or settings.database_url
    effective_echo = echo if echo is not None else settings.database_echo

    old_engine = engine
    _initialize_engine(url, echo=effective_echo)

    global _shared_initialized
    _shared_initialized = False
    _tenant_initialized.clear()

    if old_engine is not engine:

        def _dispose() -> None:
            asyncio.run(old_engine.dispose())

        _run_in_thread(_dispose)


async def dispose_engine() -> None:
    """Dispose the global SQLAlchemy engine to close open connections."""

    await engine.dispose()


def supports_schemas() -> bool:
    """Return whether the current dialect exposes schema-level separation."""

    return _SUPPORTS_SCHEMAS


def default_schema_name() -> str:
    """Return the default schema name used for shared objects."""

    return _DEFAULT_SCHEMA_NAME


__all__ = [
    "AsyncSessionLocal",
    "configure_engine",
    "dispose_engine",
    "default_schema_name",
    "SessionLocal",
    "TenantBase",
    "SharedBase",
    "engine",
    "supports_schemas",
    "session_scope",
    "get_session",
    "resolve_tenant_schema",
    "with_tenant_session",
]
