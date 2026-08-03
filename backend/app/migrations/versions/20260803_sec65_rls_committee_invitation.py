"""SEC-65 хвост: RLS для committee_meeting_invitation (создана в cmt03).

cmt03 создала tenant-таблицу без вооружения RLS — сторож
``tests/test_rls_coverage.py`` красный. Паттерн — как в ops71_import_batch:
ENABLE + FORCE + policy tenant_isolation (PG-only, SQLite не умеет RLS).
"""

from __future__ import annotations

from alembic import op

revision = "20260803_sec65_rls_committee_invitation"
down_revision = "20260803_cmt03_committee_invitations_quorum"
branch_labels = None
depends_on = None

_TABLE = "committee_meeting_invitation"
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(f'ALTER TABLE "{_TABLE}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY "{_POLICY}" ON "{_TABLE}" '
        f"FOR ALL USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{_TABLE}"')
    op.execute(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY')
