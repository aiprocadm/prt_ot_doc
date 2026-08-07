"""Pin test for RB-002g — dev_bootstrap.bootstrap_admin_user must set Tenant.code.

The Tenant.code column is NOT NULL in the Postgres migration even though the
SQLAlchemy model declares it nullable. All other tenant-creating paths in
this codebase set `code=<slug>`. dev_bootstrap was the lone outlier and
caused IntegrityError on api-1 startup once iter-18 unblocked the bootstrap
path. This pin asserts the regression cannot return.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEV_BOOTSTRAP_FILE = ROOT / "backend" / "app" / "services" / "dev_bootstrap.py"


def _find_tenant_constructor_kwargs() -> set[str]:
    """Parse dev_bootstrap.py and return the kwargs of the Tenant(...) call
    inside bootstrap_admin_user. There should be exactly one such call."""
    tree = ast.parse(DEV_BOOTSTRAP_FILE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.AsyncFunctionDef) and node.name == "bootstrap_admin_user"):
            continue
        for sub in ast.walk(node):
            if (
                isinstance(sub, ast.Call)
                and isinstance(sub.func, ast.Name)
                and sub.func.id == "Tenant"
            ):
                return {kw.arg for kw in sub.keywords if kw.arg is not None}
    raise AssertionError(
        "Tenant(...) call inside bootstrap_admin_user not found in dev_bootstrap.py"
    )


def test_dev_bootstrap_tenant_constructor_sets_code() -> None:
    """RB-002g — dev_bootstrap must pass `code` to Tenant() so the Postgres
    NOT NULL constraint on `tenant.code` is satisfied during admin bootstrap."""
    kwargs = _find_tenant_constructor_kwargs()
    assert "code" in kwargs, (
        "Tenant() constructor in dev_bootstrap.bootstrap_admin_user must set "
        "`code=<slug>` to satisfy the NOT NULL constraint on tenant.code in PG. "
        "Other tenant creators (demo_bootstrap.py, tenants/bootstrap/service.py, "
        "routes/tenants.py) all set this. See RB-002g in iter-18 plan."
    )


def test_dev_bootstrap_tenant_constructor_sets_required_columns() -> None:
    """Sanity: ensure the other minimum required columns are still being set."""
    kwargs = _find_tenant_constructor_kwargs()
    required = {"code", "slug", "name", "contact_email", "schema_name", "is_active"}
    missing = required - kwargs
    assert not missing, f"Tenant() constructor in dev_bootstrap missing required kwargs: {missing}"
