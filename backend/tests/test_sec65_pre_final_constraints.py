"""SEC-65 pre-final schema repairs — db-marked (PostgreSQL only).

Pins the three schema defects fixed by ``20260726_sec65_pre_final_constraints``:

* the forgotten global ``UNIQUE (code)`` on ``authz_roles`` is gone, so two tenants can
  hold the same role code — the shape ``services/authz_seed.py`` assumes and the reason
  provisioning a second tenant used to die on duplicate key;
* ``outbox_events`` legacy rows carrying a tenant slug/code are rewritten to ``tenant.id``
  and the missing foreign key now blocks the regression;
* ``event_id`` uniqueness is per tenant again, not global.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

PREV_REVISION = "20260726_sec65_rls_audit_export_logs"


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


async def _seed_tenant(conn, *, tenant_id: str, slug: str, code: str) -> None:
    await conn.execute(
        'INSERT INTO tenant (id, code, slug, name, contact_email, kind, schema_name, '
        'is_active, settings, created_at, updated_at, version) '
        "VALUES ($1, $2, $3, $4, $5, 'customer', $6, TRUE, '{}', now(), now(), 1)",
        tenant_id,
        code,
        slug,
        slug.title(),
        f"{slug}@example.com",
        f"tenant_{slug}",
    )


async def _seed_outbox_event(conn, *, row_id: str, tenant_ref: str, event_id: str) -> None:
    await conn.execute(
        "INSERT INTO outbox_events "
        "(id, tenant_id, event_type, aggregate_type, event_id, payload, status, attempts, "
        " created_at, updated_at, version) "
        "VALUES ($1, $2, 'demo.event', 'demo', $3, '{}', 'pending', 0, now(), now(), 1)",
        row_id,
        tenant_ref,
        event_id,
    )


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pre-final schema guard")
def test_legacy_constraints_are_repaired() -> None:
    async def _check() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            names = {
                r["conname"]
                for r in await conn.fetch(
                    "SELECT conname FROM pg_constraint WHERE conrelid IN "
                    "('authz_roles'::regclass, 'outbox_events'::regclass)"
                )
            }
            assert "authz_roles_code_key" not in names, "legacy global UNIQUE(code) still present"
            assert "uq_authz_roles_tenant_code" in names, "per-tenant role uniqueness missing"
            assert "uq_outbox_event_event" not in names, "global UNIQUE(event_id) still present"
            assert "uq_outbox_event_tenant_event" in names, "per-tenant event uniqueness missing"
            assert "fk_outbox_events_tenant" in names, "outbox_events tenant FK missing"
        finally:
            await conn.close()

    dbname = f"sec65_pre_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_check())
    finally:
        _teardown(dbname)


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pre-final schema guard")
def test_two_tenants_can_share_a_role_code() -> None:
    """The defect this migration removes: seeding the same role for a second tenant."""

    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())

    async def _check() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            await _seed_tenant(conn, tenant_id=tenant_a, slug="alpha", code="alpha")
            await _seed_tenant(conn, tenant_id=tenant_b, slug="beta", code="beta")
            for tid in (tenant_a, tenant_b):
                await conn.execute(
                    "INSERT INTO authz_roles (id, tenant_id, code, name, is_system, "
                    "created_at, updated_at, version) "
                    "VALUES ($1, $2, 'ot_lead', 'OT lead', FALSE, now(), now(), 1)",
                    str(uuid.uuid4()),
                    tid,
                )
            assert await conn.fetchval("SELECT count(*) FROM authz_roles WHERE code='ot_lead'") == 2
        finally:
            await conn.close()

    dbname = f"sec65_pre_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_check())
    finally:
        _teardown(dbname)


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the pre-final schema guard")
def test_outbox_events_legacy_tenant_slug_is_backfilled() -> None:
    tenant_id = str(uuid.uuid4())
    by_slug, by_code, by_id = (str(uuid.uuid4()) for _ in range(3))

    async def _seed_legacy() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            await _seed_tenant(conn, tenant_id=tenant_id, slug="acme", code="acme-code")
            for row_id, tenant_ref in ((by_slug, "acme"), (by_code, "acme-code"), (by_id, tenant_id)):
                await _seed_outbox_event(
                    conn, row_id=row_id, tenant_ref=tenant_ref, event_id=str(uuid.uuid4())
                )
        finally:
            await conn.close()

    async def _assert_healed() -> None:
        import asyncpg

        conn = await asyncpg.connect(f"{_sync_base()}/{dbname}")
        try:
            rows = await conn.fetch("SELECT id, tenant_id FROM outbox_events")
            assert {r["id"]: r["tenant_id"] for r in rows} == {
                by_slug: tenant_id,
                by_code: tenant_id,
                by_id: tenant_id,
            }
            # per-tenant uniqueness: the same event_id may now exist for another tenant
            other = str(uuid.uuid4())
            await _seed_tenant(conn, tenant_id=other, slug="other", code="other")
            shared_event = await conn.fetchval("SELECT event_id FROM outbox_events LIMIT 1")
            await _seed_outbox_event(
                conn, row_id=str(uuid.uuid4()), tenant_ref=other, event_id=shared_event
            )
        finally:
            await conn.close()

    dbname = f"sec65_pre_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname, PREV_REVISION)
        asyncio.run(_seed_legacy())
        _upgrade(dbname)
        asyncio.run(_assert_healed())
    finally:
        _teardown(dbname)
