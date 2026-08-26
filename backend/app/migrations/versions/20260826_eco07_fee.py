"""eco07: плата за НВОС — справочник ставок и строки расчёта (разд. 55.3).

Ставки вносятся, а не зашиты в код: их устанавливает Правительство и меняет
ежегодно постановлением. Справочник отдельно, строки расчёта отдельно — одна
ставка используется во многих строках и кварталах.

Две уникальности НА УРОВНЕ БД, обе осмысленные:

* ставка одна на «год + вид воздействия + предмет»: две ставки на одно вещество
  в одном году означали бы два разных постановления;
* строка расчёта одна на «год + квартал + вид + предмет»: кварталы — это
  авансовые платежи, и два разных значения массы за один квартал по одному
  веществу — ошибка ввода.

Сумма платы В ТАБЛИЦЕ НЕ ХРАНИТСЯ: ставку правят задним числом, и сохранённая
сумма пережила бы исправление. Считается при чтении.

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260826_eco07_fee
Revises: 20260826_sec65_rls_water
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260826_eco07_fee"
down_revision = "20260826_sec65_rls_water"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nvos_fee_rate",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("impact_kind", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("rate_per_ton", sa.Numeric(14, 2), nullable=False),
        sa.Column("source_document", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "year", "impact_kind", "subject", name="uq_fee_rate_subject"
        ),
    )
    op.create_index("ix_fee_rate_tenant_year", "nvos_fee_rate", ["tenant_id", "year"])

    op.create_table(
        "nvos_fee_line",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("impact_kind", sa.String(length=16), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("mass_tons", sa.Numeric(16, 3), nullable=False),
        sa.Column(
            "coefficient", sa.Numeric(6, 2), nullable=False, server_default="1.00"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "year",
            "quarter",
            "impact_kind",
            "subject",
            name="uq_fee_line_period",
        ),
    )
    op.create_index("ix_fee_line_tenant_year", "nvos_fee_line", ["tenant_id", "year"])


def downgrade() -> None:
    op.drop_index("ix_fee_line_tenant_year", table_name="nvos_fee_line")
    op.drop_table("nvos_fee_line")
    op.drop_index("ix_fee_rate_tenant_year", table_name="nvos_fee_rate")
    op.drop_table("nvos_fee_rate")
