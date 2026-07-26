"""SEC-65 RLS — approvals/EDO/search slice — db-marked (PostgreSQL only).

Confirms the ``20260726_sec65_rls_approvals_edo_search`` migration armed all 19
approvals/EDO/search/signature tables with RLS + FORCE + the ``tenant_isolation``
policy, and that its data-heal step rewrites legacy ``edo_messages`` rows whose
``tenant_id`` held the tenant slug/code (they would otherwise become invisible
under the id-based policy predicate). Policy semantics are proven generically in
``test_rls_committees.py`` (identical predicate).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

PREV_REVISION = "20260725_sec65_rls_ot_ops"

DOMAIN_TABLES = (
    "approval_decision_logs",
    "approval_decisions",
    "approval_instance_steps",
    "approval_instances",
    "approval_processes",
    "approval_requests",
    "approval_route_steps",
    "approval_routes",
    "approval_tasks",
    "edo_messages",
    "edo_receipts",
    "edo_status_events",
    "edo_status_history",
    "edo_webhook_inbox",
    "search_documents",
    "search_index_entries",
    "search_recent_queries",
    "search_saved_queries",
    "signature_requests",
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


def _upgrade(dbname: str, revision: str = "heads") -> None:
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = _async_url(dbname)
    get_settings.cache_clear()
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "backend" / "app" / "migrations" / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "backend" / "app" / "migrations"))
    command.upgrade(cfg, revision)


def _teardown(dbname: str) -> None:
    asyncio.run(_admin_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    os.environ.pop("DATABASE_URL", None)
    from app.core.config import get_settings

    get_settings.cache_clear()


async def _insert_minimal(conn, table: str, values: dict[str, str]) -> None:
    """INSERT with the given raw-SQL values, first asserting they cover every
    NOT NULL column without a default (so schema drift fails loudly, not with an
    opaque IntegrityError)."""

    cols = {
        r["column_name"]: r
        for r in await conn.fetch(
            "SELECT column_name, is_nullable, column_default FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = $1",
            table,
        )
    }
    assert cols, f"table {table} missing"
    required = {
        name for name, r in cols.items() if r["is_nullable"] == "NO" and r["column_default"] is None
    }
    missing = required - values.keys()
    assert not missing, f"{table}: no test value for NOT NULL columns {sorted(missing)}"
    use = {name: sql for name, sql in values.items() if name in cols}
    col_list = ", ".join(f'"{name}"' for name in use)
    val_list = ", ".join(use.values())
    await conn.execute(f'INSERT INTO "{table}" ({col_list}) VALUES ({val_list})')


@pytest.mark.skipif(
    not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the RLS approvals/EDO/search guard"
)
def test_migration_arms_all_domain_tables() -> None:
    async def _run() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            for table in DOMAIN_TABLES:
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

    dbname = f"rls_apedo_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname)


@pytest.mark.skipif(
    not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the RLS approvals/EDO/search guard"
)
def test_migration_backfills_legacy_edo_tenant_slug() -> None:
    tenant_id = str(uuid.uuid4())
    row_by_slug = str(uuid.uuid4())
    row_by_code = str(uuid.uuid4())
    row_by_id = str(uuid.uuid4())

    async def _seed_legacy() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            await _insert_minimal(
                conn,
                "tenant",
                {
                    "id": f"'{tenant_id}'",
                    "code": "'acme-code'",
                    "slug": "'acme'",
                    "name": "'Acme'",
                    "contact_email": "'acme@example.com'",
                    "kind": "'customer'",
                    "schema_name": "'tenant_acme'",
                    "is_active": "TRUE",
                    "settings": "'{}'",
                    "created_at": "now()",
                    "updated_at": "now()",
                    "version": "1",
                },
            )
            for row_id, legacy_tenant in (
                (row_by_slug, "acme"),
                (row_by_code, "acme-code"),
                (row_by_id, tenant_id),
            ):
                await _insert_minimal(
                    conn,
                    "edo_messages",
                    {
                        "id": f"'{row_id}'",
                        "tenant_id": f"'{legacy_tenant}'",
                        "direction": "'outgoing'",
                        "provider_code": "'diadoc'",
                        "status": "'queued'",
                        "payload_json": "'{}'",
                        "created_at": "now()",
                        "updated_at": "now()",
                        "version": "1",
                    },
                )
        finally:
            await conn.close()

    async def _assert_backfilled() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            rows = await conn.fetch("SELECT id, tenant_id FROM edo_messages ORDER BY id")
            got = {r["id"]: r["tenant_id"] for r in rows}
            assert got == {
                row_by_slug: tenant_id,
                row_by_code: tenant_id,
                row_by_id: tenant_id,
            }
        finally:
            await conn.close()

    dbname = f"rls_apedo_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname, PREV_REVISION)
        asyncio.run(_seed_legacy())
        _upgrade(dbname)
        asyncio.run(_assert_backfilled())
    finally:
        _teardown(dbname)
