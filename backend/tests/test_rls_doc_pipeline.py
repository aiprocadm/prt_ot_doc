"""SEC-65 RLS — document-pipeline slice — db-marked (PostgreSQL only).

Confirms the ``20260724_sec65_rls_doc_pipeline`` migration armed all 34 files/packages/
pipeline/templates/workflow tables with RLS + FORCE + the ``tenant_isolation`` policy.
Policy semantics are proven generically in ``test_rls_committees.py`` (identical predicate).
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("TEST_PG_ADMIN_URL")

DOMAIN_TABLES = (
    "file",
    "file_content_index",
    "file_download_logs",
    "file_links",
    "file_objects",
    "file_scan_results",
    "file_text_index",
    "file_versions",
    "files",
    "pack_run_items",
    "pack_run_logs",
    "pack_runs",
    "package_events",
    "package_preset_items",
    "package_presets",
    "package_presets_v2",
    "package_profiles",
    "package_profiles_v2",
    "package_read_models",
    "package_requirements",
    "package_runs",
    "packagepreset",
    "packageprofile",
    "pipeline_profiles",
    "pipeline_runs",
    "pipeline_step_locks",
    "template",
    "templateusage",
    "templateversion",
    "workflow_definition_versions",
    "workflow_definitions",
    "workflow_instances",
    "workflow_tasks",
    "workflow_timeline_events",
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


def _teardown(dbname: str) -> None:
    asyncio.run(_admin_exec(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
    os.environ.pop("DATABASE_URL", None)
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.mark.skipif(not ADMIN_URL, reason="set TEST_PG_ADMIN_URL to run the RLS doc-pipeline guard")
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

    dbname = f"rls_pipe_{uuid.uuid4().hex[:12]}"
    asyncio.run(_admin_exec(f'CREATE DATABASE "{dbname}"'))
    try:
        _upgrade(dbname)
        asyncio.run(_run())
    finally:
        _teardown(dbname)
