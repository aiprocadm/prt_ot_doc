"""mc03: managed_client_context_session — срок жизни работы «от имени» (BIZ-49 срез-10).

Доп. №3 разд. 63.2: «сессия имперсонации истекает (напр. 60 мин), не навсегда».
Additive. Tenant-таблица, поэтому RLS вооружается ЗДЕСЬ ЖЕ (урок cmt03).

Выход из контекста закрывает строку (``ended_at``), а не удаляет её: журнал
доступа к своим данным клиент вправе запросить (разд. 66), а удалённая сессия
не отвечает на вопрос «кто и когда работал от моего имени».
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260805_mc03_managed_client_context_session"
down_revision = "20260804_mc02_managed_client_access"
branch_labels = None
depends_on = None

_TABLE = "managed_client_context_session"
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
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_reason", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_mc_context_session_active",
        _TABLE,
        ["tenant_id", "user_id", "managed_client_id", "started_at"],
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
    op.drop_index("ix_mc_context_session_active", table_name=_TABLE)
    op.drop_table(_TABLE)
