"""eco05: план-график замеров ПЭК и сами замеры (разд. 55.2).

Строка плана — на пару «источник + вещество», как и норматив: замеряют
конкретное вещество на конкретном источнике. Уникальность пары держит БАЗА:
две строки плана на одно вещество означали бы два разных графика.

У замера ссылка на строку плана НЕОБЯЗАТЕЛЬНА (``plan_id`` nullable): замер по
предписанию надзорного органа делают вне графика, и отказывать ему в записи
нельзя.

Превышение в таблице НЕ ХРАНИТСЯ — это сравнение двух внесённых чисел, и
норматив со временем меняется; храни мы вывод, он пережил бы новый норматив.

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260826_eco05_pek
Revises: 20260826_sec65_rls_emissions
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260826_eco05_pek"
down_revision = "20260826_sec65_rls_emissions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emission_monitoring_plan",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("emission_source.id"),
            nullable=False,
        ),
        sa.Column("substance", sa.String(length=255), nullable=False),
        sa.Column("periodicity_months", sa.Integer(), nullable=False),
        sa.Column("next_due_on", sa.Date(), nullable=False),
        sa.Column("method", sa.String(length=255), nullable=True),
        sa.Column("laboratory", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            "substance",
            name="uq_monitoring_plan_substance",
        ),
    )
    op.create_index(
        "ix_emission_monitoring_plan_source_id",
        "emission_monitoring_plan",
        ["source_id"],
    )
    op.create_index(
        "ix_monitoring_plan_tenant_due",
        "emission_monitoring_plan",
        ["tenant_id", "next_due_on"],
    )

    op.create_table(
        "emission_measurement",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "plan_id",
            sa.String(length=36),
            sa.ForeignKey("emission_monitoring_plan.id"),
            nullable=True,
        ),
        sa.Column(
            "source_id",
            sa.String(length=36),
            sa.ForeignKey("emission_source.id"),
            nullable=False,
        ),
        sa.Column("substance", sa.String(length=255), nullable=False),
        sa.Column("measured_on", sa.Date(), nullable=False),
        sa.Column("value_grams_per_second", sa.Numeric(14, 6), nullable=False),
        sa.Column("protocol_number", sa.String(length=64), nullable=True),
        sa.Column("laboratory", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_emission_measurement_plan_id", "emission_measurement", ["plan_id"]
    )
    op.create_index(
        "ix_emission_measurement_source_id", "emission_measurement", ["source_id"]
    )
    op.create_index(
        "ix_emission_measurement_tenant_date",
        "emission_measurement",
        ["tenant_id", "measured_on"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_emission_measurement_tenant_date", table_name="emission_measurement"
    )
    op.drop_index("ix_emission_measurement_source_id", table_name="emission_measurement")
    op.drop_index("ix_emission_measurement_plan_id", table_name="emission_measurement")
    op.drop_table("emission_measurement")
    op.drop_index(
        "ix_monitoring_plan_tenant_due", table_name="emission_monitoring_plan"
    )
    op.drop_index(
        "ix_emission_monitoring_plan_source_id", table_name="emission_monitoring_plan"
    )
    op.drop_table("emission_monitoring_plan")
