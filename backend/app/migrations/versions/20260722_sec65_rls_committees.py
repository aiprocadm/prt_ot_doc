"""SEC-65: RLS second-line tenant isolation — pilot on the committees family.

Revision ID: 20260722_sec65_rls_committees
Revises: 20260719_bg02_budget_reimbursement
Create Date: 2026-07-22

Enables PostgreSQL Row-Level Security on the 8 committee* tables as a defense-in-depth
layer *beneath* the app-level ``WHERE tenant_id = …`` filtering: even a query that
forgets the filter cannot read/write another tenant's rows. Pilot scope (per approved
design ``docs/superpowers/specs/2026-07-22-sec65-rls-committees-pilot-design.md``);
the remaining tenant tables follow this same shape in later slices.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant``  — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (``current_setting(..., true)`` → NULL → no match),
i.e. fail-closed. ``FORCE ROW LEVEL SECURITY`` makes the policy apply even to the
table owner (otherwise RLS is a no-op when the app connects as owner).

PostgreSQL-only: RLS does not exist in SQLite, so upgrade/downgrade short-circuit on
any non-postgres dialect and the main SQLite test-suite is untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_sec65_rls_committees"
down_revision: str | Sequence[str] | None = "20260719_bg02_budget_reimbursement"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "committee",
    "committee_member",
    "committee_meeting",
    "committee_agenda_item",
    "committee_decision",
    "committee_decision_task",
    "committee_meeting_attendance",
    "committee_decision_vote",
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
