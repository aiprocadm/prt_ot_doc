"""mc04: managed_client_consent — согласие клиента на делегированный доступ (BIZ-49 срез-12).

Доп. №1 разд. 49.3 + Доп. №3 разд. 66.3: аутсорсер обрабатывает ПДн сотрудников
клиента — нужны «согласия/поручения по цепочке». Additive. Tenant-таблица,
поэтому RLS вооружается ЗДЕСЬ ЖЕ (урок cmt03).

Отзыв согласия не удаляет строку — ставит ``revoked_at``: «действовало ли
согласие, когда специалист работал в данных клиента» — вопрос, на который
платформа обязана отвечать и после отзыва.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260807_mc04_managed_client_consent"
down_revision = "20260805_mc03_managed_client_context_session"
branch_labels = None
depends_on = None

_TABLE = "managed_client_consent"
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
        sa.Column("document_ref", sa.String(length=255), nullable=False),
        sa.Column("granted_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_mc_consent_client",
        _TABLE,
        ["tenant_id", "managed_client_id", "granted_at"],
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
    op.drop_index("ix_mc_consent_client", table_name=_TABLE)
    op.drop_table(_TABLE)
