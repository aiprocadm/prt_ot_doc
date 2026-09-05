"""eco08: nvos_reporting_deadline — сроки экологической отчётности и платежей.

Доп. №1 разд. 55.3 («сроки сдачи отчётности, платежей … в общий календарь и
Attention Center») и разд. 57.2 («приближается срок сдачи 2-ТП»), срез-71.
Решение среза-23 «через существующий контур сроков» точки входа не имело:
``compliance_deadlines`` строятся только из удостоверений обучения. Теперь
срок вносит эколог — дату платформа не назначает и не вычисляет.

Состояние (предстоит/просрочено/исполнено) в таблице НЕ хранится — считается
при чтении из ``done_on`` и сегодняшнего дня.

Additive-шаг (expand, правило OPS-74 разд. 74.2 по построению). Колонка
``version`` обязательна — модель наследует VersionedMixin (канон br01). RLS —
в этой же миграции, по образцу dr01.

Revision ID: 20260905_eco08_reporting_deadline
Revises: 20260905_sec65_rls_discipline_status_report
Create Date: 2026-09-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260905_eco08_reporting_deadline"
down_revision = "20260905_sec65_rls_discipline_status_report"
branch_labels = None
depends_on = None

_TABLE = "nvos_reporting_deadline"
_INDEX = "ix_reporting_deadline_tenant_due"
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
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("period", sa.String(length=32), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("done_on", sa.Date(), nullable=True),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Календарь и Центр внимания читают «по арендатору, ближайшие сверху».
    op.create_index(_INDEX, _TABLE, ["tenant_id", "due_on"])

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
