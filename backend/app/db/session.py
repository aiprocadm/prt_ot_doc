"""Async database session management with tenant schema support."""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import AsyncIterator, Callable, Iterable
from contextlib import asynccontextmanager
from uuid import UUID

from sqlalchemy import MetaData, Table, event, or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.sql_text import (
    quote_identifier,
    session_label_params,
    session_label_statement,
)
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
        await _apply_tenant_rls(self)
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
    engine_kwargs: dict[str, object] = {"echo": echo, "future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        # aiosqlite держит по нити на соединение; отменённый посреди DB-операции
        # запрос (request-timeout middleware, обрыв клиента) оставляет соединение
        # «отравленным», и следующий взявший его из пула запрос виснет намертво
        # (в тестах — спорадические 504 на тривиальных ручках). NullPool даёт
        # свежее соединение на каждый checkout — для файлового SQLite это дёшево;
        # PG-пул (prod) не затрагивается.
        engine_kwargs["poolclass"] = NullPool
    engine = create_async_engine(url, **engine_kwargs)
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


def _unicode_lower(value):
    return value.lower() if isinstance(value, str) else value


@event.listens_for(Engine, "connect")
def _teach_sqlite_unicode_lower(dbapi_connection, _record) -> None:
    """SQLite должен понижать регистр КИРИЛЛИЦЫ так же, как PostgreSQL.

    Встроенные ``lower()`` и ``LIKE`` в SQLite знают только латиницу: «ГАЗель»
    и «газель» для них разные слова. Поиск по реестрам (``ilike``)
    компилируется в ``lower(a) LIKE lower(b)``, и без подмены он вёл бы себя в
    разработке и тестах иначе, чем в бою, — расхождение, которое ловится
    только на живом сервере.

    Хук повешен на КЛАСС движка, а не на один экземпляр: тесты поднимают свой
    SQLite-движок рядом с приложением, и правило обязано действовать в обоих.
    На PostgreSQL хук молчит — у его соединения нет ``create_function``.
    """

    register = getattr(dbapi_connection, "create_function", None)
    if register is None:  # PostgreSQL и всё, что не SQLite
        return
    try:
        register("lower", 1, _unicode_lower, deterministic=True)
    except TypeError:  # старый SQLite без deterministic
        register("lower", 1, _unicode_lower)


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
    raw_slug = str(info.get("tenant_slug") or info.get("tenant") or "").strip().lower() or None
    tenant_schema = str(info.get("tenant_schema") or "").strip() or None
    # Celery tasks pass tenant UUIDs where a slug is expected
    # (``session_scope(tenant=str(tenant.id))``); a "slug" that parses as a
    # UUID is really a tenant id and must never be compared against
    # ``tenant_id`` values by the before_flush guard — resolve the real slug
    # from the Tenant row instead.
    slug_as_id = _normalize_tenant_id(raw_slug)
    tenant_slug = raw_slug if slug_as_id is None else None
    if tenant_id is None:
        tenant_id = slug_as_id

    if tenant_id is not None and slug_as_id is None:
        info["tenant_id"] = tenant_id
        if tenant_slug:
            info.setdefault("tenant_slug", tenant_slug)
        if tenant_schema:
            info.setdefault("tenant_schema", tenant_schema)
        return tenant_id, tenant_slug, tenant_schema

    if tenant_id is None and not tenant_slug:
        return None, None, tenant_schema

    try:
        from app.models.models import Tenant
    except Exception:
        return tenant_id, tenant_slug, tenant_schema

    conditions = []
    if tenant_id is not None:
        conditions.append(Tenant.id == tenant_id)
    if tenant_slug:
        conditions.extend((Tenant.slug == tenant_slug, Tenant.code == tenant_slug))

    row = (
        session.connection()
        .execute(select(Tenant.id, Tenant.slug, Tenant.schema_name).where(or_(*conditions)))
        .first()
    )
    if row is None:
        if tenant_id is not None:
            info["tenant_id"] = tenant_id
        return tenant_id, tenant_slug, tenant_schema

    tenant_id = str(row.id)
    resolved_slug = str(row.slug).strip().lower()
    resolved_schema = str(row.schema_name or tenant_schema or "").strip() or None
    info["tenant_id"] = tenant_id
    info["tenant_slug"] = resolved_slug
    info["tenant"] = resolved_slug
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
    # Celery tasks pass tenant UUIDs where a slug is expected
    # (``tenant_context(tenant_id)`` + ``session_scope(tenant=tenant_id)``,
    # see audit_export_job). The UUID then lands in ``tenant_slug`` and the
    # schema/search_path derived from it are bogus — distrust them and
    # resolve the real identity from the Tenant row by id.
    slug_as_id = _normalize_tenant_id(tenant_slug)
    stale_schema = tenant_schema(tenant_slug) if slug_as_id is not None else None
    if stale_schema and tenant_schema_name == stale_schema:
        tenant_schema_name = None

    if tenant_id and tenant_slug and tenant_schema_name and slug_as_id is None:
        info["tenant_id"] = tenant_id
        info["tenant_slug"] = tenant_slug
        info["tenant_schema"] = tenant_schema_name
        info["tenant"] = tenant_slug
        return tenant_id, tenant_slug, tenant_schema_name

    filters = []
    if tenant_id:
        filters.append(Tenant.id == tenant_id)
    if slug_as_id is not None and slug_as_id != tenant_id:
        filters.append(Tenant.id == slug_as_id)
    if tenant_slug and slug_as_id is None:
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
    resolved_tenant_schema = str(
        row.schema_name or tenant_schema_name or tenant_schema(resolved_tenant_slug)
    ).strip()
    info["tenant_id"] = resolved_tenant_id
    info["tenant_slug"] = resolved_tenant_slug
    info["tenant_schema"] = resolved_tenant_schema
    info["tenant"] = resolved_tenant_slug
    if stale_schema:
        # Replace the schema derived from the mislabelled slug before
        # _apply_search_path (which runs after hydration in __aenter__)
        # sends the bogus "tenant_<uuid>" entry to Postgres.
        search_path = info.get("search_path")
        if isinstance(search_path, list) and stale_schema in search_path:
            info["search_path"] = [
                resolved_tenant_schema if entry == stale_schema else entry for entry in search_path
            ]
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
                    lambda sync_conn: TenantBase.metadata.create_all(sync_conn, tables=tables)
                )
        finally:
            for table in mirrored:
                TenantBase.metadata.remove(table)


async def _create_tenant_schema(schema: str) -> None:
    """Create database objects for an individual tenant schema."""

    if not _SUPPORTS_SCHEMAS:
        return
    quoted_schema = quote_identifier(schema, source="схема арендатора")
    quoted_shared = quote_identifier(_SHARED_SCHEMA, source="общая схема из настроек")
    async with engine.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {quoted_schema}"))
        search_path_sql = f"SET LOCAL search_path TO {quoted_schema}, {quoted_shared}"
        if _SEARCH_PATH_SUPPORTED:
            # iter-16f part 4 set this on the async conn, but FK to unqualified
            # ``tenant`` still failed in CI — the async→sync greenlet bridge
            # used by run_sync may not propagate session-scoped SET reliably.
            # Apply SET LOCAL on both sides of the bridge and verify.
            await conn.execute(text(search_path_sql))
            applied_async = (await conn.execute(text("SHOW search_path"))).scalar_one()
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
    if schema_name is None and _normalize_tenant_id(slug) is not None:
        # ``slug`` is actually a tenant UUID (celery-task calling convention);
        # deriving a schema from it would bootstrap a spurious empty
        # "tenant_<uuid>" schema. Session hydration resolves the real schema
        # from the Tenant row instead.
        _logger.warning("tenant.schema.ensure.uuid_slug_skipped", extra={"slug": slug})
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
    if schema_name is None and _normalize_tenant_id(slug) is not None:
        # Same guard as ensure_tenant_schema: never derive a schema name
        # from a tenant UUID mislabelled as slug.
        _logger.warning("tenant.schema.ensure.uuid_slug_skipped", extra={"slug": slug})
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
            # Имя схемы параметром не передать, поэтому — проверка формата
            # перед склейкой (разд. 64.1, строка «Injection»).
            normalized.append(quote_identifier(schema, source="search_path сессии"))
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
        # Разд. 64.1, строка «Injection»: метка сессии приходит ИЗ ЗАГОЛОВКА
        # ЗАПРОСА. Здесь она уходит параметром и текстом SQL не становится —
        # см. `app/core/sql_text.py`.
        await session.execute(session_label_statement(), session_label_params(ctx.correlation_id))


async def _apply_tenant_rls(session: AsyncSession) -> None:
    """Set the SEC-65 row-level-security GUCs so Postgres policies enforce tenant
    isolation as a second line of defense (independent of app-level filtering).

    No-op on non-Postgres (SQLite tests have no RLS). ``set_config(name, value,
    is_local=True)`` is transaction-scoped and parameter-safe, so nothing leaks
    across pooled connections. A trusted session (``rls_bypass=True``) flips
    ``app.bypass_rls`` on; otherwise ``app.current_tenant`` is pinned to the
    session tenant (empty when absent → policies deny → fail-closed).
    """

    if not _SUPPORTS_SCHEMAS:
        return
    info = session.info if isinstance(session.info, dict) else {}
    if info.get("rls_bypass"):
        await session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        return
    tenant_id = str(info.get("tenant_id") or "").strip()
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": tenant_id},
    )


async def rearm_session_tenant_context(session: AsyncSession) -> None:
    """Re-apply the transaction-local tenant context to an already-open session.

    ``SET LOCAL search_path`` and the SEC-65 RLS GUCs (``_apply_tenant_rls``)
    only live until the next commit/rollback; ``TenantAsyncSession.__aenter__``
    applies them once, so a handler that explicitly ends a transaction and keeps
    using the session continues on a context-less transaction — under FORCE RLS
    its reads turn empty and writes are rejected. Call this after such a
    commit/rollback to re-pin the context. Safe to call mid-transaction (the
    ``SET LOCAL``/``set_config`` calls are idempotent).
    """

    await _apply_search_path(session)
    await _apply_tenant_rls(session)


def AsyncSessionLocal(
    *,
    tenant: str | None = None,
    tenant_id: str | None = None,
    schema_name: str | None = None,
    include_public: bool = True,
    create_schema: bool = True,
    rls_bypass: bool = False,
) -> AsyncSession:
    """Build a tenant-aware session optionally creating schemas on demand.

    ``rls_bypass=True`` marks the session as a trusted system/cross-tenant scope
    (SEC-65): it sets ``app.bypass_rls='on'`` so Postgres row-level policies let
    all rows through. Use only for seeders / background jobs that legitimately
    operate outside a single tenant; leave ``False`` for tenant-scoped work.
    """

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
    session.info["rls_bypass"] = rls_bypass
    normalized_tenant_id = _normalize_tenant_id(tenant_id)
    if normalized_tenant_id is not None:
        session.info["tenant_id"] = normalized_tenant_id
    elif tenant is not None:
        normalized_from_tenant = _normalize_tenant_id(tenant)
        if normalized_from_tenant is not None:
            session.info["tenant_id"] = normalized_from_tenant
    return session


@asynccontextmanager
async def transaction_scope(session: AsyncSession) -> AsyncIterator[AsyncSession]:
    """Own the transaction for an existing session: commit on clean exit, roll back on error.

    Single source of truth for the request-transaction contract. Both the API
    dependency (``app.api.dependencies.get_session``) and the test double in
    ``tests/conftest.py`` route through this, so the harness cannot drift into
    being more forgiving than production — the divergence that let flush-only
    handlers return 2xx while discarding their writes.
    """

    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise


@asynccontextmanager
async def session_scope(
    *, tenant: str | None = None, schema_name: str | None = None, rls_bypass: bool = False
) -> AsyncIterator[AsyncSession]:
    """Provide a transactional scope around operations executed per tenant.

    ``schema_name`` overrides the default-tenant → shared-schema short-circuit
    in :func:`AsyncSessionLocal`. Pass it when the tenant slug equals
    ``DEFAULT_TENANT_SLUG`` but the data actually lives in a tenant-specific
    schema (e.g. ``bootstrap_demo_tenant`` after ``aensure_tenant_schema``
    creates ``tenant_demo.*``).
    """

    async with AsyncSessionLocal(
        tenant=tenant, schema_name=schema_name, rls_bypass=rls_bypass
    ) as session:
        async with transaction_scope(session):
            yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a tenant-aware session."""

    async with session_scope() as session:
        yield session


@asynccontextmanager
async def with_tenant_session(
    *, tenant_id: str, schema_name: str | None = None
) -> AsyncIterator[AsyncSession]:
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

    async with AsyncSessionLocal(
        tenant=tenant, tenant_id=tenant_id, schema_name=schema_name
    ) as session:
        if _SEARCH_PATH_SUPPORTED:
            schema = schema_name or tenant_schema(tenant or tenant_id or _DEFAULT_TENANT_SLUG)
            path = _format_search_path([schema, _SHARED_SCHEMA])
            try:
                await session.execute(text(f"SET LOCAL search_path TO {path}"))
            except Exception:
                await session.execute(text(f"SET search_path TO {path}"))
            ctx = get_tenant_context()
            if ctx and ctx.correlation_id:
                # Второй путь тех же настроек сессии. Урок среза-206: у доставки
                # было два пути, правило стояло на одном — правило ставится на ОБА.
                await session.execute(
                    session_label_statement(), session_label_params(ctx.correlation_id)
                )
        try:
            yield session
        finally:
            if _SEARCH_PATH_SUPPORTED:
                try:
                    shared = _format_search_path([_SHARED_SCHEMA])
                    await session.execute(text(f"SET search_path TO {shared}"))
                except Exception:
                    pass


def configure_engine(*, database_url: str | None = None, echo: bool | None = None) -> None:
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
    "transaction_scope",
    "get_session",
    "resolve_tenant_schema",
    "with_tenant_session",
]
