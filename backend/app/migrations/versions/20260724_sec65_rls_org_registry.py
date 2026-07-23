"""SEC-65: RLS second-line tenant isolation — org-structure registry backbone.

Revision ID: 20260724_sec65_rls_org_registry
Revises: 20260723_sec65_rls_sout_risk_contractors_budget
Create Date: 2026-07-24

Arms the shared org-structure backbone — the tables many domains hang off:
``company``, ``branch``, ``site``, ``department``, ``position``, ``person``,
``asset``, ``equipment``, ``workplace`` (9 tables). Takes RLS coverage from 73 to 82.

Write-path analysis (extra care — these are base tables written from many places):
  * Request handlers (companies/branches/sites/persons/departments/workplaces APIs,
    ``repository.create_company``) get their session from ``api/dependencies.py::get_session``,
    which pins ``app.current_tenant`` to the request tenant; the row's ``tenant_id``
    equals it, so WITH CHECK passes.
  * Domain writers that create ``person``/``workplace`` (``services/sout_import.py``,
    ``modules/incidents/operations.py``) open no session of their own — they receive the
    caller's tenant-scoped session.
  * The demo seeder already runs with ``rls_bypass=True`` (its ``_seed_committees_demo``
    creates ``person`` rows, and committee tables are already RLS-armed and seed fine).
  * **Cross-tenant provisioning** was the one path that FORCE RLS would break: creating a
    new tenant inserts that tenant's ``company`` on a tenant-less ``tenant="public"``
    shared session, where ``app.current_tenant`` is empty so ``tenant_id = ''`` fails the
    predicate. Fixed in the same change by adding ``rls_bypass=True`` to both provisioning
    sessions (``api/routes/platform_tenants.py`` and ``scripts/bootstrap_tenant.py``) —
    the legitimate trusted cross-tenant case the mechanism is designed for.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes
it apply even to the table owner. PostgreSQL-only.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260724_sec65_rls_org_registry"
down_revision: str | Sequence[str] | None = "20260723_sec65_rls_sout_risk_contractors_budget"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "company",
    "branch",
    "site",
    "department",
    "position",
    "person",
    "asset",
    "equipment",
    "workplace",
)

_POLICY = "tenant_isolation"

_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in _TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{_POLICY}" ON "{table}" '
            f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    for table in reversed(_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
