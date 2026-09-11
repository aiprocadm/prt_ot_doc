from __future__ import annotations

import asyncio
import socket
from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings
from app.db.base import TARGET_METADATA

config = context.config
settings = get_settings()
config.set_main_option("sqlalchemy.url", settings.alembic_database_url)

if config.config_file_name is not None:
    # Срез-146: по умолчанию fileConfig ВЫКЛЮЧАЕТ все уже созданные логгеры
    # (`disable_existing_loggers=True`). В одном процессе с тестами это гасит
    # `app.services.webhooks` и прочие логгеры продукта после первого
    # `alembic upgrade` на PostgreSQL — и caplog дальше ничего не ловит.
    fileConfig(config.config_file_name, disable_existing_loggers=False)


target_metadata = TARGET_METADATA


async def run_migrations_online() -> None:
    connectable: AsyncEngine = create_async_engine(
        # SEC-65: the owner role, not the runtime one — ENABLE/FORCE ROW LEVEL
        # SECURITY is owner-only DDL. Falls back to DATABASE_URL when
        # MIGRATION_DATABASE_URL is unset (single-role setups, SQLite).
        settings.migration_database_url,
        poolclass=pool.NullPool,
        future=True,
    )

    # POST-2 migration hardening: real per-migration transactions.
    # History: 2026-06-01..07-02 the whole run used isolation_level="AUTOCOMMIT"
    # (every statement committed immediately) because PG forbids *using* an enum
    # value in the transaction that ADD VALUE'd it. The accepted trade-off was
    # zero atomicity — a migration failing midway left partial state (see
    # RELEASE_BLOCKERS_STATUS "env.py atomicity review", which named this exact
    # hardening as the follow-up). Now: `transaction_per_migration=True` is a
    # REAL per-migration BEGIN/COMMIT (fail = rollback of that one migration),
    # and each of the 7 `ALTER TYPE ... ADD VALUE` sites opens its own
    # `op.get_context().autocommit_block()` — the enum extension commits
    # immediately (durable + usable by later statements/migrations) and stays
    # retry-safe via IF NOT EXISTS.
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def do_run_migrations(connection) -> None:
    _ensure_alembic_version_table_can_store_long_revisions(connection)
    # Commit the pre-step explicitly: SQLAlchemy 2.0 connections autobegin on
    # first statement, and alembic's per-migration transaction management must
    # start from a clean (non-begun) connection.
    connection.commit()
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
        transaction_per_migration=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _ensure_alembic_version_table_can_store_long_revisions(connection) -> None:
    """Make alembic_version.version_num compatible with long revision IDs.

    Alembic's default table uses VARCHAR(32), which fails for human-readable
    revision identifiers used in this repository.
    """

    table = sa.Table(
        "alembic_version",
        sa.MetaData(),
        sa.Column("version_num", sa.Text(), nullable=False, primary_key=True),
    )
    table.create(bind=connection, checkfirst=True)

    if connection.dialect.name == "postgresql":
        connection.execute(
            sa.text("ALTER TABLE alembic_version " "ALTER COLUMN version_num TYPE TEXT")
        )


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_schemas=True,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run() -> None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        try:
            asyncio.run(run_migrations_online())
        except Exception as exc:
            if _is_infrastructure_blocked_error(exc):
                print(
                    "Alembic: database host is unavailable in current "
                    "environment, falling back to offline migration mode."
                )
                return
            else:
                raise


def _is_infrastructure_blocked_error(error: Exception) -> bool:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, socket.gaierror):
            return True
        current = current.__cause__ or current.__context__
    return False


run()
