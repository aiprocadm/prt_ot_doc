#!/usr/bin/env python3
"""SEC-65: provision the unprivileged application role that RLS actually applies to.

Postgres skips row-level security for ``SUPERUSER`` and ``BYPASSRLS`` roles, even
on ``FORCE ROW LEVEL SECURITY`` tables. The stock compose stack connects as the
cluster bootstrap superuser, which makes all tenant-isolation policies inert —
this script creates the role the runtime should use instead.

Split of duties after running it:

* ``MIGRATION_DATABASE_URL`` → owner/superuser role, used by Alembic only
  (``ENABLE``/``FORCE ROW LEVEL SECURITY`` is owner-only DDL);
* ``DATABASE_URL`` → this role: ``NOSUPERUSER NOBYPASSRLS`` with plain DML rights.

Idempotent: safe to re-run. ``ALTER DEFAULT PRIVILEGES`` covers objects the owner
creates later, and re-running also repairs a role that drifted back to privileged
or tables created outside the default-privilege owner.

Usage::

    PYTHONPATH=backend python scripts/provision_app_role.py \\
        --admin-url postgresql://ptd:ptd@localhost:5432/ptd \\
        --role ptd_app --password "$APP_DB_PASSWORD"

``--admin-url`` defaults to ``MIGRATION_DATABASE_URL`` and then ``DATABASE_URL``.
Uses asyncpg, the only Postgres driver this project depends on.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from urllib.parse import urlsplit, urlunsplit


def to_asyncpg_dsn(url: str) -> str:
    """Strip the SQLAlchemy driver suffix — asyncpg.connect wants a plain DSN."""

    parts = urlsplit(url)
    scheme = parts.scheme.split("+", 1)[0]
    if scheme == "postgres":
        scheme = "postgresql"
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_statements(
    *, role: str, password: str, database: str, owner: str, schemas: list[str], exists: bool
) -> list[str]:
    """SQL that makes ``role`` a usable, RLS-enforced application role."""

    role_ident = _quote_ident(role)
    owner_ident = _quote_ident(owner)
    db_ident = _quote_ident(database)
    attributes = (
        f"LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
        f"PASSWORD {_quote_literal(password)}"
    )
    # NOSUPERUSER/NOBYPASSRLS are re-asserted on every run: a role that drifted
    # back to privileged is exactly the failure this guards against.
    statements = [
        f"{'ALTER' if exists else 'CREATE'} ROLE {role_ident} WITH {attributes}",
        f"GRANT CONNECT ON DATABASE {db_ident} TO {role_ident}",
        # Tenant provisioning creates ``tenant_<slug>`` schemas at runtime
        # (``ensure_tenant_schema``). CREATE on the database is unrelated to row
        # security — it does not let the role read another tenant's rows.
        f"GRANT CREATE ON DATABASE {db_ident} TO {role_ident}",
    ]
    for schema in schemas:
        schema_ident = _quote_ident(schema)
        statements += [
            f"GRANT USAGE ON SCHEMA {schema_ident} TO {role_ident}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_ident} "
            f"TO {role_ident}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema_ident} TO {role_ident}",
            # Objects the migration owner creates later.
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner_ident} IN SCHEMA {schema_ident} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role_ident}",
            f"ALTER DEFAULT PRIVILEGES FOR ROLE {owner_ident} IN SCHEMA {schema_ident} "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {role_ident}",
        ]
    return statements


async def provision(
    admin_url: str, role: str, password: str, *, schemas: list[str] | None = None
) -> list[str]:
    """Create/repair the application role. Returns the statements applied."""

    import asyncpg

    conn = await asyncpg.connect(to_asyncpg_dsn(admin_url))
    try:
        database = await conn.fetchval("SELECT current_database()")
        owner = await conn.fetchval("SELECT current_user")
        if schemas is None:
            schemas = [
                row["nspname"]
                for row in await conn.fetch(
                    "SELECT nspname FROM pg_namespace "
                    "WHERE nspname = 'public' OR nspname LIKE 'tenant\\_%' ORDER BY nspname"
                )
            ]
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", role) is not None

        statements = build_statements(
            role=role,
            password=password,
            database=database,
            owner=owner,
            schemas=schemas,
            exists=exists,
        )
        for statement in statements:
            await conn.execute(statement)

        check = await conn.fetchrow(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = $1", role
        )
        if check["rolsuper"] or check["rolbypassrls"]:  # pragma: no cover - defensive
            raise SystemExit(
                f"role {role!r} is still SUPERUSER/BYPASSRLS after provisioning; "
                "row-level security would not apply"
            )
        print(
            f"OK: role {role} is NOSUPERUSER NOBYPASSRLS on database {database} "
            f"(schemas: {', '.join(schemas) or 'none'}); point DATABASE_URL at it "
            f"and keep {owner} for MIGRATION_DATABASE_URL."
        )
        return statements
    finally:
        await conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--admin-url",
        default=os.getenv("MIGRATION_DATABASE_URL") or os.getenv("DATABASE_URL"),
        help="DSN of the owner/superuser role (default: MIGRATION_DATABASE_URL, DATABASE_URL)",
    )
    parser.add_argument("--role", default=os.getenv("APP_DB_USER", "ptd_app"))
    parser.add_argument("--password", default=os.getenv("APP_DB_PASSWORD"))
    parser.add_argument(
        "--schema",
        action="append",
        dest="schemas",
        help="schema to grant on (repeatable); default: public + existing tenant_* schemas",
    )
    args = parser.parse_args(argv)

    if not args.admin_url:
        parser.error("--admin-url is required (or set MIGRATION_DATABASE_URL/DATABASE_URL)")
    if not args.password:
        parser.error("--password is required (or set APP_DB_PASSWORD)")
    if not args.admin_url.startswith(("postgresql", "postgres:")):
        print("skip: not a PostgreSQL database — row-level security does not apply")
        return 0

    asyncio.run(provision(args.admin_url, args.role, args.password, schemas=args.schemas))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI helper
    sys.exit(main())
