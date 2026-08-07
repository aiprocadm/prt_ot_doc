"""DB guard: full ``alembic upgrade heads`` must succeed on a fresh Postgres.

This is the ONLY test that exercises migrations against real PG enum types.
The rest of the suite runs on SQLite, where ``Enum`` columns degrade to
VARCHAR and accept any string — which is exactly why a stack of PG-only
migration bugs (enum ``server_default`` case-mismatch, unsafe new enum value
usage, enum-type ordering) shipped undetected and broke backend boot on PG.

Skips unless ``TEST_PG_ADMIN_URL`` points at a Postgres superuser/owner
connection (a maintenance DB such as .../postgres) able to CREATE/DROP
databases. Locally: ``postgresql://postgres:postgres@localhost:5432/postgres``.
CI sets it to the job's Postgres service.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")
REPO_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = REPO_ROOT / "backend" / "app" / "migrations" / "alembic.ini"
SCRIPT_LOCATION = REPO_ROOT / "backend" / "app" / "migrations"


def _async_url(admin_url: str, dbname: str) -> str:
    base = admin_url.rsplit("/", 1)[0]  # strip the maintenance db segment
    base = base.replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{dbname}"


@pytest.mark.skipif(
    not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the Postgres migration guard"
)
def test_alembic_upgrade_heads_on_fresh_postgres() -> None:
    import asyncpg
    from alembic import command
    from alembic.config import Config

    dbname = f"alembic_guard_{uuid.uuid4().hex[:12]}"

    async def _exec(sql: str) -> None:
        conn = await asyncpg.connect(ADMIN_URL)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        os.environ["DATABASE_URL"] = _async_url(ADMIN_URL, dbname)
        # env.py reads settings.database_url; settings is cached — force a re-read.
        from app.core.config import get_settings

        get_settings.cache_clear()

        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
        command.upgrade(cfg, "heads")  # raises on the first failing migration
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()


@pytest.mark.skipif(
    not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the Postgres migration guard"
)
def test_alembic_downgrade_base_then_reupgrade_on_fresh_postgres() -> None:
    """Full reversibility: ``upgrade heads`` -> ``downgrade base`` -> ``upgrade heads``.

    The suite is SQLite-only, so downgrade-path bugs surface only on real
    Postgres. Two classes this guards against:

    * a downgrade that fails outright (e.g. shrinking
      ``alembic_version.version_num`` below the length of a live revision id);
    * a downgrade that leaves state behind so the *re-upgrade* collides
      (e.g. a ``CREATE TYPE`` with no matching ``DROP TYPE`` on downgrade).
    """
    import asyncpg
    from alembic import command
    from alembic.config import Config

    dbname = f"alembic_rt_{uuid.uuid4().hex[:12]}"

    async def _exec(sql: str) -> None:
        conn = await asyncpg.connect(ADMIN_URL)
        try:
            await conn.execute(sql)
        finally:
            await conn.close()

    asyncio.run(_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        os.environ["DATABASE_URL"] = _async_url(ADMIN_URL, dbname)
        from app.core.config import get_settings

        get_settings.cache_clear()

        cfg = Config(str(ALEMBIC_INI))
        cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
        command.upgrade(cfg, "heads")
        command.downgrade(cfg, "base")  # raises on the first failing downgrade
        command.upgrade(cfg, "heads")  # raises if a downgrade left undropped state
    finally:
        asyncio.run(_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
