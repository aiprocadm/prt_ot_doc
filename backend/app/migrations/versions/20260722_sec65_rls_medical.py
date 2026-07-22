"""SEC-65: RLS second-line tenant isolation — extend to the medical domain.

Revision ID: 20260722_sec65_rls_medical
Revises: 20260722_sec65_rls_committees
Create Date: 2026-07-22

Applies the same PostgreSQL Row-Level Security shape proven in the committees pilot
(``20260722_sec65_rls_committees``) to the 7 medical-oversight tables. Medical exams,
fitness verdicts, referrals and suspensions carry sensitive health personal data, so a
DB-enforced second line of tenant isolation is especially warranted here.

Mechanism (see ``backend/app/db/session.py::_apply_tenant_rls``):
  - ``app.current_tenant`` — GUC pinned to the session tenant per transaction.
  - ``app.bypass_rls``      — ``'on'`` for trusted system/cross-tenant seeders/jobs.
Policy denies when neither is set (fail-closed). ``FORCE ROW LEVEL SECURITY`` makes it
apply even to the table owner.

PostgreSQL-only: upgrade/downgrade short-circuit on any non-postgres dialect, so the
SQLite test-suite is untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_sec65_rls_medical"
down_revision: str | Sequence[str] | None = "20260722_sec65_rls_committees"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (
    "medical_exam",
    "medical_norm",
    "medical_factor",
    "medical_referral",
    "medical_suspension",
    "psychiatric_activity_type",
    "psychiatric_position_activity",
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
