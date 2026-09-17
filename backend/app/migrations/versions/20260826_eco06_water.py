"""eco06: водопользование — точки и помесячный учёт объёмов (разд. 55.2).

Водозабор и выпуск сточных вод лежат в ОДНОМ реестре с закрытым типом: поля у
них одни и те же, а тип нужен ровно для того, чтобы объёмы не смешивались в
сводке — это разные величины, и складывать их нельзя.

Две уникальности НА УРОВНЕ БД, обе осмысленные:

* номер точки уникален В ПРЕДЕЛАХ ОБЪЕКТА (как номер источника выбросов);
* учёт помесячный: «точка + год + месяц» уникальна, две записи за один месяц по
  одной точке — ошибка ввода, а не два разных факта.

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260826_eco06_water
Revises: 20260826_sec65_rls_pek
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260826_eco06_water"
down_revision = "20260826_sec65_rls_pek"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "water_usage_point",
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
            "facility_id",
            sa.String(length=36),
            sa.ForeignKey("nvos_facility.id"),
            nullable=False,
        ),
        sa.Column("point_number", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("water_body", sa.String(length=255), nullable=True),
        sa.Column("permit_number", sa.String(length=64), nullable=True),
        sa.Column("permit_valid_until", sa.Date(), nullable=True),
        sa.Column("annual_limit_cubic_meters", sa.Numeric(16, 3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "facility_id", "point_number", name="uq_water_point_number"
        ),
    )
    op.create_index("ix_water_usage_point_facility_id", "water_usage_point", ["facility_id"])
    op.create_index(
        "ix_water_point_tenant_permit",
        "water_usage_point",
        ["tenant_id", "permit_valid_until"],
    )

    op.create_table(
        "water_usage_record",
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
            "point_id",
            sa.String(length=36),
            sa.ForeignKey("water_usage_point.id"),
            nullable=False,
        ),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_month", sa.Integer(), nullable=False),
        sa.Column("volume_cubic_meters", sa.Numeric(16, 3), nullable=False),
        sa.Column("basis", sa.String(length=16), nullable=False),
        sa.Column("meter_number", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "point_id",
            "period_year",
            "period_month",
            name="uq_water_record_period",
        ),
    )
    op.create_index("ix_water_usage_record_point_id", "water_usage_record", ["point_id"])
    op.create_index(
        "ix_water_record_tenant_year",
        "water_usage_record",
        ["tenant_id", "period_year"],
    )


def downgrade() -> None:
    op.drop_index("ix_water_record_tenant_year", table_name="water_usage_record")
    op.drop_index("ix_water_usage_record_point_id", table_name="water_usage_record")
    op.drop_table("water_usage_record")
    op.drop_index("ix_water_point_tenant_permit", table_name="water_usage_point")
    op.drop_index("ix_water_usage_point_facility_id", table_name="water_usage_point")
    op.drop_table("water_usage_point")
