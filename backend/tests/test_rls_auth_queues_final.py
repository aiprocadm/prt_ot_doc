"""SEC-65 FINAL slice — auth path, tokens and infra queues — db-marked (PostgreSQL only).

Two things are pinned here:

* every table of the last slice is armed (RLS + FORCE + the shared ``tenant_isolation``
  predicate), and the shadow ``webhook_subscriptions`` table is gone;
* the policies actually isolate on the REAL tables — checked under a throwaway
  ``NOSUPERUSER`` role, because a superuser ignores row security even with FORCE, and the
  functional suite runs on SQLite where the RLS hooks are no-ops. Without this test
  nothing in the repository would notice if the predicate stopped working on ``user`` /
  ``api_key`` / ``refresh_session``.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

DOMAIN_TABLES = (
    "api_key",
    "api_tokens",
    "authz_policies",
    "authz_role_permissions",
    "authz_roles",
    "authz_user_roles",
    "idempotency_keys",
    "inbound_webhook_dedup",
    "outbox",
    "outbox_events",
    "refresh_session",
    "user",
    "user_attribute",
    "user_role",
    "webhook_subscription",
)

# Tables the isolation probe writes into. Kept small on purpose: the predicate is
# identical everywhere, so proving it on the auth-critical trio is enough.
PROBE_TABLES = ("user", "api_key", "refresh_session")


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
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = _async_url(dbname)
    get_settings.cache_clear()
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "app" / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "app" / "migrations"))
    command.upgrade(cfg, "heads")


def _teardown(dbname: str, role: str | None = None) -> None:
    if role:
        # Roles are cluster-global and survive DROP DATABASE. Cleanup must never mask the
        # test's own failure: if the body died before CREATE ROLE, these are no-ops.
        for statement in (f'DROP OWNED BY "{role}"', f'DROP ROLE IF EXISTS "{role}"'):
            try:
                asyncio.run(_admin_exec(statement))
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
    asyncio.run(_admin_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    os.environ.pop("DATABASE_URL", None)
    from app.core.config import get_settings

    get_settings.cache_clear()


async def _required_columns(conn, table: str) -> set[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = $1 "
        "AND is_nullable = 'NO' AND column_default IS NULL",
        table,
    )
    return {r["column_name"] for r in rows}


async def _insert_row(conn, table: str, values: dict[str, str]) -> None:
    """INSERT raw-SQL values, asserting they cover every NOT NULL column without a
    default — so schema drift fails loudly instead of as an opaque IntegrityError."""

    missing = await _required_columns(conn, table) - values.keys()
    assert not missing, f"{table}: no test value for NOT NULL columns {sorted(missing)}"
    cols = ", ".join(f'"{c}"' for c in values)
    vals = ", ".join(values.values())
    await conn.execute(f'INSERT INTO "{table}" ({cols}) VALUES ({vals})')


async def _seed_tenant(conn, *, tenant_id: str, slug: str) -> None:
    await _insert_row(
        conn,
        "tenant",
        {
            "id": f"'{tenant_id}'",
            "code": f"'{slug}'",
            "slug": f"'{slug}'",
            "name": f"'{slug.title()}'",
            "contact_email": f"'{slug}@example.com'",
            "kind": "'customer'",
            "schema_name": f"'tenant_{slug}'",
            "is_active": "TRUE",
            "settings": "'{}'",
            "created_at": "now()",
            "updated_at": "now()",
            "version": "1",
        },
    )


async def _seed_auth_rows(conn, *, tenant_id: str, marker: str) -> str:
    """One user + one API key + one refresh session for a tenant. Returns the user id."""

    user_id = str(uuid.uuid4())
    await _insert_row(
        conn,
        "user",
        {
            "id": f"'{user_id}'",
            "tenant_id": f"'{tenant_id}'",
            "email": f"'{marker}@example.com'",
            "full_name": f"'{marker.title()} User'",
            "hashed_password": "'x'",
            "role": "'admin'",
            "is_active": "TRUE",
            "created_at": "now()",
            "updated_at": "now()",
            "version": "1",
        },
    )
    await _insert_row(
        conn,
        "api_key",
        {
            "id": f"'{uuid.uuid4()}'",
            "tenant_id": f"'{tenant_id}'",
            "name": f"'{marker}-key'",
            "key_prefix": f"'{marker[:8]}'",
            "key_hash": "'hash'",
            "is_active": "TRUE",
            "usage_count": "0",
            "created_at": "now()",
            "updated_at": "now()",
            "version": "1",
        },
    )
    await _insert_row(
        conn,
        "refresh_session",
        {
            "id": f"'{uuid.uuid4()}'",
            "tenant_id": f"'{tenant_id}'",
            "user_id": f"'{user_id}'",
            "token_jti": f"'{uuid.uuid4()}'",
            "family_id": f"'{uuid.uuid4()}'",
            "expires_at": "now() + interval '1 day'",
            "created_at": "now()",
            "updated_at": "now()",
            "version": "1",
        },
    )
    return user_id


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the final RLS guard")
def test_migration_arms_all_domain_tables() -> None:
    async def _run() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            for table in DOMAIN_TABLES:
                cls = await conn.fetchrow(
                    "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                    "WHERE relname = $1 AND relnamespace = 'public'::regnamespace",
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

            # authz_permissions stays exempt by design (platform-wide catalogue).
            armed = await conn.fetchval(
                "SELECT relrowsecurity FROM pg_class WHERE relname = 'authz_permissions'"
            )
            assert armed is False, "authz_permissions must stay exempt — see rls_policy.py"

            # the model-less shadow table is dropped by this migration
            assert (
                await conn.fetchval("SELECT to_regclass('public.webhook_subscriptions')") is None
            ), "shadow table webhook_subscriptions should have been dropped"
        finally:
            await conn.close()

    dbname = f"rls_final_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname)


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the final RLS guard")
def test_auth_tables_isolate_tenants_under_unprivileged_role() -> None:
    """The real check: a non-superuser session sees only its own tenant's auth rows."""

    role = f"rls_final_{uuid.uuid4().hex[:8]}"
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())

    async def _run() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            # Superuser setup — it bypasses RLS, so both tenants' rows land fine.
            await _seed_tenant(conn, tenant_id=tenant_a, slug="alpha")
            await _seed_tenant(conn, tenant_id=tenant_b, slug="beta")
            await _seed_auth_rows(conn, tenant_id=tenant_a, marker="alpha")
            await _seed_auth_rows(conn, tenant_id=tenant_b, marker="beta")

            await conn.execute(f'CREATE ROLE "{role}" NOSUPERUSER')
            await conn.execute(f'GRANT USAGE ON SCHEMA public TO "{role}"')
            for table in PROBE_TABLES:
                await conn.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON "{table}" TO "{role}"')

            # Drop privileges: from here on the policies are actually enforced.
            await conn.execute(f'SET ROLE "{role}"')

            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
            for table in PROBE_TABLES:
                seen = await conn.fetch(f'SELECT tenant_id FROM "{table}"')
                assert [r["tenant_id"] for r in seen] == [
                    tenant_a
                ], f"{table}: tenant A must see exactly its own row, got {seen}"

            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_b)
            for table in PROBE_TABLES:
                assert await conn.fetchval(f'SELECT count(*) FROM "{table}"') == 1

            # No tenant context and no bypass → fail-closed.
            await conn.execute("SELECT set_config('app.current_tenant', '', false)")
            for table in PROBE_TABLES:
                assert await conn.fetchval(f'SELECT count(*) FROM "{table}"') == 0

            # WITH CHECK: tenant A cannot plant a row owned by tenant B.
            await conn.execute("SELECT set_config('app.current_tenant', $1, false)", tenant_a)
            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                await _insert_row(
                    conn,
                    "api_key",
                    {
                        "id": f"'{uuid.uuid4()}'",
                        "tenant_id": f"'{tenant_b}'",
                        "name": "'sneak'",
                        "key_prefix": "'sneak'",
                        "key_hash": "'hash'",
                        "is_active": "TRUE",
                        "usage_count": "0",
                        "created_at": "now()",
                        "updated_at": "now()",
                        "version": "1",
                    },
                )

            # Trusted system scope still sees everything.
            await conn.execute("SELECT set_config('app.bypass_rls', 'on', false)")
            assert await conn.fetchval('SELECT count(*) FROM "user"') == 2
            await conn.execute("SELECT set_config('app.bypass_rls', 'off', false)")
        finally:
            await conn.execute("RESET ROLE")
            await conn.close()

    dbname = f"rls_final_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname, role=role)
