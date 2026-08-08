"""mc05: managed_client_transfer — журнал переноса данных клиента (BIZ-49 срез-14).

Разд. 49.1: перенос данных клиента в его собственный арендатор «без потери
истории». Журнал фиксирует, что, когда и кем перенесено, и соответствие
старых id новым (без него timeline не сшить). Additive. Tenant-таблица,
поэтому RLS вооружается ЗДЕСЬ ЖЕ (урок cmt03).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260808_mc05_managed_client_transfer"
down_revision = "20260807_mc04_managed_client_consent"
branch_labels = None
depends_on = None

_TABLE = "managed_client_transfer"
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
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
            index=True,
        ),
        sa.Column("target_tenant_slug", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="completed"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("counts", sa.JSON(), nullable=False),
        sa.Column("id_map", sa.JSON(), nullable=False),
    )

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
    if bind.dialect.name == "postgresql":
        op.execute(f'DROP POLICY IF EXISTS "{_POLICY}" ON "{_TABLE}"')
    op.drop_table(_TABLE)
