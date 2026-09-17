"""cf04: client_audit_report — отчёты авто-аудита клиента (BIZ-51 срез-7).

Доп. №1 разд. 51.3. Additive: новая таблица, существующие данные не трогаются.

Tenant-таблица, поэтому RLS вооружается ЗДЕСЬ ЖЕ (правило проекта, урок cmt03).

Revision ID: 20260818_cf04_client_audit_report
Revises: 20260817_cf03_client_change_source_ref_width
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260818_cf04_client_audit_report"
down_revision = "20260817_cf03_client_change_source_ref_width"
branch_labels = None
depends_on = None

_TABLE = "client_audit_report"
_INDEX = "ix_client_audit_report_feed"
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    op.create_table(
        _TABLE,
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "managed_client_id",
            sa.String(length=36),
            sa.ForeignKey("managed_client.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("overall", sa.String(length=16), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    # Отчёты читаются по клиенту, свежие сверху; тем же индексом ищется
    # «отчёт за период уже есть» при дедупликации тика.
    op.create_index(_INDEX, _TABLE, ["tenant_id", "managed_client_id", "period_end"])

    if not is_pg:
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
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{_TABLE}"')
    op.drop_index(_INDEX, table_name=_TABLE)
    op.drop_table(_TABLE)
