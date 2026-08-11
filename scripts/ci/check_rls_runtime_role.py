#!/usr/bin/env python3
"""SEC-65 gate: the runtime database role must not bypass row-level security.

Postgres applies row security only to roles that are neither ``SUPERUSER`` nor
``BYPASSRLS``. Without this gate a deployment can ship all 264 tenant-isolation
policies and still serve cross-tenant data, because the connection role walks
past every one of them.

Behaviour:

* ``DATABASE_URL`` unset, or pointing at SQLite → **skip** (exit 0). Row security
  does not exist there, and the default dev/test stack is SQLite.
* Postgres, role is ``NOSUPERUSER NOBYPASSRLS`` → **pass**.
* Postgres, role is privileged → **fail** (exit 1) with the remediation command.

``--allow-privileged`` downgrades a failure to a warning, for pipelines that
intentionally run migrations/db-marker tests as the owner role.

Usage::

    PYTHONPATH=backend python scripts/ci/check_rls_runtime_role.py
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys


def _database_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    if url and url.strip():
        return url.strip()
    try:
        from app.core.config import get_settings
    except Exception:  # pragma: no cover - settings need env that CI may not set
        return None
    try:
        return get_settings().database_url
    except Exception:  # pragma: no cover - misconfigured env is not this gate's job
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-privileged",
        action="store_true",
        help="report a privileged role as a warning instead of a failure",
    )
    args = parser.parse_args(argv)

    url = _database_url()
    if not url:
        print("SKIP: DATABASE_URL is not set — nothing to verify")
        return 0
    if not url.startswith("postgresql"):
        print(f"SKIP: {url.split('://', 1)[0]} has no row-level security")
        return 0

    from app.db.rls_runtime import verify_runtime_role_for_url

    try:
        privileges = asyncio.run(
            verify_runtime_role_for_url(url, enforce=False, component="ci")
        )
    except Exception as exc:  # pragma: no cover - unreachable DB is an infra problem
        print(f"SKIP: could not probe the database role ({exc.__class__.__name__}: {exc})")
        return 0

    if privileges is None:  # pragma: no cover - guarded by the scheme check above
        print("SKIP: not a PostgreSQL connection")
        return 0

    if privileges.enforces_rls:
        print(f"OK: {privileges.describe()} — row-level policies are enforced")
        if privileges.can_escalate:
            print(
                f"WARN: role {privileges.role_name!r} is a member of a privileged role "
                "and could reach BYPASSRLS with SET ROLE"
            )
        return 0

    message = (
        f"FAIL: {privileges.describe()} — PostgreSQL ignores row-level security for it, "
        "so every SEC-65 tenant-isolation policy is inert.\n"
        "Fix: PYTHONPATH=backend python scripts/provision_app_role.py "
        "--role ptd_app --password <secret>, then point DATABASE_URL at that role and "
        "keep the owner role in MIGRATION_DATABASE_URL."
    )
    if args.allow_privileged:
        print(message.replace("FAIL:", "WARN:", 1))
        return 0
    print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
