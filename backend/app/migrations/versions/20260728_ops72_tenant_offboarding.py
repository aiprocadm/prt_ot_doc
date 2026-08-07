"""OPS-72 (разд. 72.3): жизненный цикл офбординга арендатора.

Revision ID: 20260728_ops72_tenant_offboarding
Revises: 20260728_sec68_portal_token_usage
Create Date: 2026-07-28

Карта состояний разд. 72.1 содержит две стадии, которых в продукте не было:
«офбординг» и «пост-офбординг». ``tenant_offboarding`` — заявка на расторжение,
grace-период и акт об удалении.

Запись остаётся ПОСЛЕ удаления данных: акт — это ответ на вопрос «что именно вы
стёрли и когда», и он нужен ровно тогда, когда самих данных уже нет.

Таблица tenant-scoped, поэтому армируется RLS в этой же миграции (SEC-65):
арендатор видит свой статус, управляющий тенант работает через bypass-сессию
флота. Реестр: 276 → 277 enabled.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260728_ops72_tenant_offboarding"
down_revision: str | Sequence[str] | None = "20260728_sec68_portal_token_usage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Имя таблицы дублируется литералом в вызовах op.*: аудит миграций
# (scripts/audit/column_drift_lite.py) разбирает файлы статически через AST и
# НЕ видит колонок, если имя передано переменной — тогда таблица выглядит как
# «модель есть, миграции нет». Константа остаётся для RLS-выражений.
_TABLE = "tenant_offboarding"
_POLICY = "tenant_isolation"
_PREDICATE = (
    "current_setting('app.bypass_rls', true) = 'on' "
    "OR tenant_id = current_setting('app.current_tenant', true)"
)


def upgrade() -> None:
    op.create_table(
        "tenant_offboarding",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(36),
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="grace"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("grace_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("grace_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("purge_act", sa.JSON(), nullable=True),
        sa.Column(
            "requested_by_user_id",
            sa.String(36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("requested_by_email", sa.String(255), nullable=True),
        # Колонка оптимистичной блокировки из TenantBaseModel.
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_tenant_offboarding_tenant_status",
        "tenant_offboarding",
        ["tenant_id", "status"],
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
    op.drop_index("ix_tenant_offboarding_tenant_status", table_name="tenant_offboarding")
    op.drop_table("tenant_offboarding")
