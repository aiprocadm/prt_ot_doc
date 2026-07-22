"""SEC-65 RLS coverage guard tests.

``test_rls_coverage_registry_consistent`` runs the ratchet purely from metadata (no DB)
and is the guard that fails a PR which adds a tenant table without classifying it.

``test_rls_enabled_matches_postgres`` (``-m db``) upgrades a throwaway PostgreSQL to heads
and asserts the live set of RLS-armed tables equals ``RLS_ENABLED_TABLES`` — so the
registry can never drift from what the migrations actually did.
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import uuid
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GUARD_PATH = _REPO_ROOT / "scripts" / "audit" / "check_rls_coverage.py"


def _load_guard():
    spec = importlib.util.spec_from_file_location("check_rls_coverage", _GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_rls_coverage_registry_consistent() -> None:
    """Every tenant table is classified; no overlaps; no stale names."""
    errors = _load_guard().check()
    assert errors == [], "RLS coverage guard drift:\n" + "\n".join(errors)


# ---- db-marked cross-check: registry must match the live catalog ----

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")


def _sync_base() -> str:
    return ADMIN_URL.rsplit("/", 1)[0]


def _async_url(dbname: str) -> str:
    base = _sync_base().replace("postgresql://", "postgresql+asyncpg://", 1)
    return f"{base}/{dbname}"


async def _admin_exec(sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(ADMIN_URL)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def _upgrade(dbname: str) -> None:
    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = _async_url(dbname)
    get_settings.cache_clear()
    cfg = Config(str(_REPO_ROOT / "backend" / "app" / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(_REPO_ROOT / "backend" / "app" / "migrations"))
    command.upgrade(cfg, "heads")


@pytest.mark.db
@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to cross-check RLS coverage")
def test_rls_enabled_matches_postgres() -> None:
    from app.core.rls_policy import RLS_ENABLED_TABLES

    async def _live_rls_tables() -> set[str]:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            rows = await conn.fetch(
                "SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity"
            )
        finally:
            await conn.close()
        return {r["relname"] for r in rows}

    dbname = f"rls_cov_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        live = asyncio.run(_live_rls_tables())
        assert live == set(RLS_ENABLED_TABLES), (
            "registry vs live RLS drift — "
            f"only in registry: {sorted(set(RLS_ENABLED_TABLES) - live)}; "
            f"only in DB: {sorted(live - set(RLS_ENABLED_TABLES))}"
        )
    finally:
        asyncio.run(_admin_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        os.environ.pop("DATABASE_URL", None)
        from app.core.config import get_settings

        get_settings.cache_clear()
