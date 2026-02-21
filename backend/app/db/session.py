"""Async database session management with tenant schema support."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager

from sqlalchemy import MetaData, Table, event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.tenant import get_current_tenant, tenant_schema

_settings = get_settings()
_DEFAULT_TENANT_SLUG = _settings.default_tenant_slug
_SHARED_SCHEMA = _settings.shared_schema


class TenantAsyncSession(AsyncSession):
    """Async session that applies the tenant search path on entry."""

    async def __aenter__(self) -> TenantAsyncSession:  # type: ignore[override]
        await super().__aenter__()
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


def _apply_default_tenant(session, flush_context, instances) -> None:
    """Populate ``tenant_id`` on new tenant-scoped models if missing."""

    tenant_slug: str | None = session.info.get("tenant")
    if not tenant_slug:
        return

    for obj in session.new:
        if getattr(obj.__class__, "__tenant_model__", False):
            current = getattr(obj, "tenant_id", None)
            if current:
                continue
            setattr(obj, "tenant_id", tenant_slug)


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
        clone = table.tometadata(TenantBase.metadata)
        mirrored.append(clone)
    return mirrored


async def _create_shared_schema() -> None:
    """Create database objects stored in the shared schema."""

    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        mirrored = _mirror_shared_tables_for_creation()

        try:
            if not _SUPPORTS_SCHEMAS:
                await conn.run_sync(TenantBase.metadata.create_all)
        finally:
            for table in mirrored:
                TenantBase.metadata.remove(table)


async def _create_tenant_schema(schema: str) -> None:
    """Create database objects for an individual tenant schema."""

    if not _SUPPORTS_SCHEMAS:
        return
    async with engine.begin() as conn:
        await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        if _SEARCH_PATH_SUPPORTED:
            await conn.execute(text(f'SET search_path TO "{schema}"'))
        await conn.run_sync(TenantBase.metadata.create_all)


def ensure_shared_schema() -> None:
    """Ensure shared tables are present during local development."""

    global _shared_initialized
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


def ensure_tenant_schema(slug: str) -> None:
    """Ensure tenant-specific tables exist for the provided slug."""

    if not _SUPPORTS_SCHEMAS:
        return
    schema = tenant_schema(slug)
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
    await session.execute(text(f"SET search_path TO {formatted}"))


def AsyncSessionLocal(
    *,
    tenant: str | None = None,
    schema_name: str | None = None,
    include_public: bool = True,
    create_schema: bool = True,
) -> AsyncSession:
    """Build a tenant-aware session optionally creating schemas on demand."""

    ensure_shared_schema()
    slug = tenant or get_current_tenant().slug
    if _SUPPORTS_SCHEMAS:
        if schema_name:
            schema = schema_name
            slug = tenant or get_current_tenant().slug
        elif slug != _DEFAULT_TENANT_SLUG:
            if create_schema:
                ensure_tenant_schema(slug)
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
    return session


@asynccontextmanager
async def session_scope(*, tenant: str | None = None) -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around operations executed per tenant."""

    async with AsyncSessionLocal(tenant=tenant) as session:
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


SessionLocal = AsyncSessionLocal


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
]
