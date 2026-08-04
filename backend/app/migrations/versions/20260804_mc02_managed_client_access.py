"""mc02: managed_client_access — матрица «специалист → клиент» (BIZ-49 срез-6, разд. 49.3).

Additive. Tenant-таблица, поэтому RLS вооружается ЗДЕСЬ ЖЕ (урок cmt03).
Отзыв гранта — колонка ``revoked_at``, не удаление строки: трассируемость
действий аутсорсера в данных клиента требует, чтобы след оставался.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260804_mc02_managed_client_access"
down_revision = "20260804_mc01_managed_client"
branch_labels = None
depends_on = None

_TABLE = "managed_client_access"
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
        sa.Column(
            "user_id",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("all_modules", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("modules", sa.JSON(), nullable=False),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_managed_client_access_client_user",
        _TABLE,
        ["tenant_id", "managed_client_id", "user_id"],
    )
    op.create_index("ix_managed_client_access_user", _TABLE, ["tenant_id", "user_id"])

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
    op.drop_index("ix_managed_client_access_user", table_name=_TABLE)
    op.drop_index("ix_managed_client_access_client_user", table_name=_TABLE)
    op.drop_table(_TABLE)
