"""SEC-65 RLS pilot — db-marked (PostgreSQL only; RLS does not exist in SQLite).

Two guards on a throwaway PG upgraded to heads:
  1. The migration actually armed all 8 committee tables (RLS + FORCE + the
     ``tenant_isolation`` policy referencing both GUCs).
  2. The policy predicate enforces isolation: own tenant visible, other tenant
     invisible, no context → zero rows (fail-closed), bypass → all rows, and a
     cross-tenant INSERT is rejected by WITH CHECK.

The test connection is a PG superuser (``TEST_PG_ADMIN_URL``), which *bypasses*
RLS — so the enforcement test drops to a fresh NOSUPERUSER role via ``SET ROLE``
before asserting visibility. Skips unless ``TEST_PG_ADMIN_URL`` is set.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

COMMITTEE_TABLES = (
    "committee",
    "committee_member",
    "committee_meeting",
    "committee_agenda_item",
    "committee_decision",
    "committee_decision_task",
    "committee_meeting_attendance",
    "committee_decision_vote",
)

# Must mirror ``_PREDICATE`` in the migration 20260722_sec65_rls_committees.py.
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


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
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "app" / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "app" / "migrations"))
    command.upgrade(cfg, "heads")


def _teardown(dbname: str) -> None:
    asyncio.run(_admin_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    os.environ.pop("DATABASE_URL", None)
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the RLS pilot guard")
def test_migration_arms_all_committee_tables() -> None:
    async def _run() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            for table in COMMITTEE_TABLES:
                cls = await conn.fetchrow(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = $1",
                    table,
                )
                assert cls is not None, f"table {table} missing"
                assert cls["relrowsecurity"], f"RLS not enabled on {table}"
                assert cls["relforcerowsecurity"], f"FORCE RLS not set on {table}"
                using = await conn.fetchval(
                    """
                    SELECT pg_get_expr(p.polqual, p.polrelid)
                    FROM pg_policy p JOIN pg_class c ON c.oid = p.polrelid
                    WHERE c.relname = $1 AND p.polname = 'tenant_isolation'
                    """,
                    table,
                )
                assert using is not None, f"tenant_isolation policy missing on {table}"
                assert "app.current_tenant" in using and "app.bypass_rls" in using
                assert "tenant_id" in using
        finally:
            await conn.close()

    dbname = f"rls_arm_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname)


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the RLS pilot guard")
def test_policy_enforces_tenant_isolation() -> None:
    async def _run() -> None:
        import asyncpg

        role = f"rls_probe_{uuid.uuid4().hex[:8]}"
        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:  # noqa: PLR1702
            # Superuser setup: throwaway table with the migration's exact predicate.
            await conn.execute(
                "CREATE TABLE rls_probe (id serial PRIMARY KEY, tenant_id text NOT NULL, v text)"
            )
            await conn.execute("ALTER TABLE rls_probe ENABLE ROW LEVEL SECURITY")
            await conn.execute("ALTER TABLE rls_probe FORCE ROW LEVEL SECURITY")
            await conn.execute(
                f"CREATE POLICY tenant_isolation ON rls_probe FOR ALL "
                f"USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
            )
            # Superuser bypasses RLS → seed rows for two tenants.
            await conn.execute(
                "INSERT INTO rls_probe (tenant_id, v) VALUES ('A','a1'),('A','a2'),('B','b1')"
            )
            await conn.execute(f'CREATE ROLE "{role}" NOSUPERUSER')
            await conn.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            await conn.execute(f'GRANT SELECT, INSERT ON rls_probe TO "{role}"')
            await conn.execute(f'GRANT USAGE, SELECT ON SEQUENCE rls_probe_id_seq TO "{role}"')

            # Drop to a non-superuser, non-owner role: RLS now applies.
            await conn.execute(f'SET ROLE "{role}"')

            await conn.execute("SELECT set_config('app.current_tenant', 'A', false)")
            assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 2  # only A's rows

            await conn.execute("SELECT set_config('app.current_tenant', 'B', false)")
            assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 1  # only B's row

            # No tenant context and no bypass → fail-closed (zero rows).
            await conn.execute("SELECT set_config('app.current_tenant', '', false)")
            assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 0

            # Bypass → everything visible (trusted system session).
            await conn.execute("SELECT set_config('app.bypass_rls', 'on', false)")
            assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 3
            await conn.execute("SELECT set_config('app.bypass_rls', 'off', false)")

            # WITH CHECK: in tenant A's context, inserting a B-owned row is rejected.
            await conn.execute("SELECT set_config('app.current_tenant', 'A', false)")
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await conn.execute("INSERT INTO rls_probe (tenant_id, v) VALUES ('B','sneak')")
            # But a matching-tenant insert succeeds.
            await conn.execute("INSERT INTO rls_probe (tenant_id, v) VALUES ('A','a3')")
            assert await conn.fetchval("SELECT count(*) FROM rls_probe") == 3  # a1,a2,a3

            await conn.execute("RESET ROLE")
        finally:
            # Roles are cluster-global (survive the dropped DB) — clean up always.
            # DROP OWNED BY removes the grants that otherwise block DROP ROLE.
            try:
                await conn.execute("RESET ROLE")
                await conn.execute(f'DROP OWNED BY "{role}"')
                await conn.execute(f'DROP ROLE IF EXISTS "{role}"')
            except Exception:
                pass
            await conn.close()

    dbname = f"rls_enf_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        asyncio.run(_run())
    finally:
        _teardown(dbname)
