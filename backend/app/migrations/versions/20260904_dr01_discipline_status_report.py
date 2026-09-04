"""dr01: discipline_status_report — авто-отчёт о состоянии по дисциплинам.

Доп. №1 разд. 57.4 (срез-50): «авто-отчёты о состоянии по каждой
дисциплине для клиента при аренде». Отчёт арендатора о самом себе: снимок
разреза «по дисциплинам» на дату плюс динамика к прошлому отчёту.
Строение и защита — как у ``client_audit_report`` (cf04): та же RLS-политика,
тот же индекс «по арендатору, свежие сверху».

Additive-шаг (expand, правило OPS-74 разд. 74.2 по построению).

Revision ID: 20260904_dr01_discipline_status_report
Revises: 20260903_in01_incident_discipline
Create Date: 2026-09-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260904_dr01_discipline_status_report"
down_revision = "20260903_in01_incident_discipline"
branch_labels = None
depends_on = None

_TABLE = "discipline_status_report"
_INDEX = "ix_discipline_status_report_feed"
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
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    # Отчёты читаются свежие сверху; тем же индексом ищется «за эту дату уже
    # есть» при дедупликации тика и «предыдущий» для динамики.
    op.create_index(_INDEX, _TABLE, ["tenant_id", "period_end"])

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
