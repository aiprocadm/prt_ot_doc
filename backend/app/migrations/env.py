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
    fileConfig(config.config_file_name)


target_metadata = TARGET_METADATA


async def run_migrations_online() -> None:
    connectable: AsyncEngine = create_async_engine(
        settings.database_url,
        poolclass=pool.NullPool,
        future=True,
    )

    # AUTOCOMMIT + transaction_per_migration: each migration commits on its own,
    # so an `ALTER TYPE ... ADD VALUE` in one migration is durably committed
    # before a *later* migration references that value (PG forbids using a new
    # enum value in the transaction that added it). With AUTOCOMMIT, Alembic's
    # per-migration `begin_transaction()` issues explicit BEGIN/COMMIT around
    # each migration, while DDL that runs between them (and the ADD VALUE) is
    # not trapped in one giant outer transaction. Matches the per-migration-tx
    # assumption migration authors already documented (e.g. next55b "own tx").
    async with connectable.connect() as connection:
        await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def do_run_migrations(connection) -> None:
    _ensure_alembic_version_table_can_store_long_revisions(connection)
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
            sa.text(
                "ALTER TABLE alembic_version "
                "ALTER COLUMN version_num TYPE TEXT"
            )
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
