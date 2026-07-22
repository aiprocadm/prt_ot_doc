#!/usr/bin/env python3
"""SEC-65 RLS coverage ratchet guard.

Every tenant-scoped table (one with a ``tenant_id`` column) must be classified in
``backend/app/core/rls_policy.py`` as either RLS-enabled or explicitly exempt. This
guard fails when:

  * a tenant table is in NEITHER set (a new table slipped in without a decision),
  * a name appears in BOTH sets (contradiction),
  * a listed name is not (or no longer) a real tenant table (stale entry).

Run from the repo root with ``PYTHONPATH=backend``. Exit code 0 = clean, 1 = drift.
Pure metadata introspection — no database required, so it runs in the normal suite.
"""

from __future__ import annotations

import sys


def _ensure_all_models_imported() -> None:
    """Populate SQLAlchemy metadata with EVERY model.

    ``import app.db.base`` alone misses a few tables that only register when their
    router module is imported (e.g. ``header_footer_presets``). Building the app forces
    the full router → model graph, matching what the running app and the pytest conftest
    see, so the coverage set is stable regardless of import order.
    """
    import os

    import app.db.base  # noqa: F401

    for key in ("APP_NAME", "SECRET_KEY", "S3_ACCESS_KEY", "S3_SECRET_KEY"):
        os.environ.setdefault(key, "rls-coverage-guard")
    try:
        from app.api.app import create_app

        create_app()
    except Exception:
        # Best-effort: app.db.base already covers the vast majority; a build failure
        # here should not mask a genuine coverage drift.
        pass


def _tenant_tables() -> set[str]:
    _ensure_all_models_imported()
    from app.db.session import SharedBase, TenantBase

    tables: dict = {}
    for md in (SharedBase.metadata, TenantBase.metadata):
        tables.update(md.tables)
    return {
        name
        for name, table in tables.items()
        if any(col.name == "tenant_id" for col in table.columns)
    }


def check() -> list[str]:
    from app.core.rls_policy import RLS_ENABLED_TABLES, RLS_EXEMPT_TABLES

    tenant = _tenant_tables()
    errors: list[str] = []

    overlap = RLS_ENABLED_TABLES & RLS_EXEMPT_TABLES
    if overlap:
        errors.append(f"tables in BOTH enabled and exempt: {sorted(overlap)}")

    stale = (RLS_ENABLED_TABLES | RLS_EXEMPT_TABLES) - tenant
    if stale:
        errors.append(
            f"registry lists names that are not tenant tables (renamed/dropped?): {sorted(stale)}"
        )

    uncovered = tenant - RLS_ENABLED_TABLES - RLS_EXEMPT_TABLES
    if uncovered:
        errors.append(
            "new tenant table(s) missing from the RLS registry — arm them with RLS "
            "(add to a 20260722_sec65_rls_* migration + RLS_ENABLED_TABLES) or record "
            f"them in RLS_EXEMPT_TABLES: {sorted(uncovered)}"
        )

    return errors


def main() -> int:
    from app.core.rls_policy import RLS_ENABLED_TABLES, RLS_EXEMPT_TABLES

    errors = check()
    total = len(RLS_ENABLED_TABLES) + len(RLS_EXEMPT_TABLES)
    if errors:
        print("RLS coverage guard FAILED:")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(
        f"RLS coverage guard passed: {len(RLS_ENABLED_TABLES)} enabled / "
        f"{len(RLS_EXEMPT_TABLES)} exempt / {total} tenant tables classified."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
