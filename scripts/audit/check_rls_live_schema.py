#!/usr/bin/env python3
"""SEC-65 live-database audit: every tenant table in PostgreSQL is actually armed.

``check_rls_coverage.py`` is the ratchet guard, but it enumerates tenant tables from
**SQLAlchemy metadata**. Two blind spots follow from that, and this script closes both
by asking the database instead (``pg_attribute``: any table that has a ``tenant_id``
column is a tenant table, model or no model):

1. **Shadow tables.** A table with ``tenant_id`` but no ORM model is invisible to the
   metadata-based guard, so it never enters the denominator and can sit unarmed
   forever. ``webhook_subscriptions`` (plural) was exactly this until it was dropped.

2. **Per-tenant schemas.** The ``sec65_rls_*`` migrations arm tables in ``public``.
   On a deployment that also uses schema-per-tenant (``tenant_<slug>``), each schema
   holds its own copy of those tables — and those copies are NOT armed by the
   migrations. Run this before switching production to the unprivileged role.

Requires a reachable PostgreSQL (``DATABASE_URL``); skips otherwise, so it is safe to
wire into pipelines that run on SQLite.

Usage::

    PYTHONPATH=backend python scripts/audit/check_rls_live_schema.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from urllib.parse import urlsplit, urlunsplit

TENANT_TABLE_SQL = """
    SELECT n.nspname AS schema_name,
           c.relname AS table_name,
           c.relrowsecurity AS rls_enabled,
           c.relforcerowsecurity AS rls_forced
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind = 'r'
      AND n.nspname NOT IN ('pg_catalog', 'information_schema')
      AND NOT n.nspname LIKE 'pg_toast%'
      AND EXISTS (
          SELECT 1 FROM pg_attribute a
          WHERE a.attrelid = c.oid
            AND a.attname = 'tenant_id'
            AND a.attnum > 0
            AND NOT a.attisdropped
      )
    ORDER BY n.nspname, c.relname
"""


def _dsn(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme == "postgres":
        scheme = "postgresql"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def _database_url() -> str | None:
    url = (os.getenv("DATABASE_URL") or "").strip()
    if url:
        return url
    try:
        from app.core.config import get_settings

        return get_settings().database_url
    except Exception:  # pragma: no cover - misconfigured env is not this gate's job
        return None


async def audit(url: str) -> list[str]:
    import asyncpg

    from app.core.rls_policy import RLS_ENABLED_TABLES, RLS_EXEMPT_TABLES

    conn = await asyncpg.connect(_dsn(url))
    try:
        rows = await conn.fetch(TENANT_TABLE_SQL)
    finally:
        await conn.close()

    known = RLS_ENABLED_TABLES | RLS_EXEMPT_TABLES
    errors: list[str] = []
    shadow: list[str] = []
    unarmed_tenant_schema: list[str] = []

    for row in rows:
        schema, table = row["schema_name"], row["table_name"]
        armed = bool(row["rls_enabled"]) and bool(row["rls_forced"])

        if schema == "public":
            if table not in known:
                shadow.append(f"{schema}.{table}")
            elif table in RLS_ENABLED_TABLES and not armed:
                errors.append(
                    f"{schema}.{table}: registry says ENABLED but the table is not "
                    f"ENABLE+FORCE ROW LEVEL SECURITY (enabled={row['rls_enabled']}, "
                    f"forced={row['rls_forced']}) — a migration did not apply"
                )
        elif schema.startswith("tenant_"):
            if table in RLS_ENABLED_TABLES and not armed:
                unarmed_tenant_schema.append(f"{schema}.{table}")

    if shadow:
        errors.append(
            "table(s) with a tenant_id column that no ORM model covers, so the "
            "metadata ratchet guard cannot see them — arm them or drop them: "
            f"{sorted(shadow)}"
        )
    if unarmed_tenant_schema:
        errors.append(
            "per-tenant schema copies are NOT armed (the sec65_rls_* migrations only "
            "touch public) — arm them before pointing the runtime at the unprivileged "
            f"role, or these rows are unprotected: {sorted(unarmed_tenant_schema)}"
        )
    return errors


def main() -> int:
    url = _database_url()
    if not url:
        print("SKIP: DATABASE_URL is not set — nothing to audit")
        return 0
    if not url.startswith(("postgresql", "postgres:")):
        print(f"SKIP: {url.split('://', 1)[0]} has no row-level security")
        return 0

    try:
        errors = asyncio.run(audit(url))
    except Exception as exc:  # pragma: no cover - unreachable DB is an infra problem
        print(f"SKIP: could not audit the database ({exc.__class__.__name__}: {exc})")
        return 0

    if errors:
        print("RLS live-schema audit FAILED:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("RLS live-schema audit passed: every tenant_id table in PostgreSQL is armed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
