"""eco04: инвентаризация источников выбросов и нормативы ПДВ (разд. 55.2).

Стационарные источники (организованные и неорганизованные) с инвентаризационным
номером и нормативы выброса по парам «источник + вещество» с реквизитами
разрешения.

Две уникальности НА УРОВНЕ БД, обе осмысленные:

* номер источника уникален В ПРЕДЕЛАХ ОБЪЕКТА, а не арендатора: нумерация
  ведётся по объекту, и «источник №1» есть у каждого;
* норматив — один на пару «источник + вещество»: ПДВ устанавливается по каждому
  веществу отдельно, дубль означал бы два разных норматива на одно вещество.

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260826_eco04_emissions
Revises: 20260825_sec65_rls_waste
Create Date: 2026-08-26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260826_eco04_emissions"
down_revision = "20260825_sec65_rls_waste"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emission_source",
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
        sa.Column("source_number", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("inventoried_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "facility_id", "source_number", name="uq_emission_source_number"
        ),
    )
    op.create_index("ix_emission_source_facility_id", "emission_source", ["facility_id"])

    op.create_table(
        "emission_norm",
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
        sa.Column("limit_grams_per_second", sa.Numeric(14, 6), nullable=True),
        sa.Column("limit_tons_per_year", sa.Numeric(14, 3), nullable=True),
        sa.Column("permit_number", sa.String(length=64), nullable=True),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "source_id", "substance", name="uq_emission_norm_substance"
        ),
    )
    op.create_index("ix_emission_norm_source_id", "emission_norm", ["source_id"])
    op.create_index("ix_emission_norm_tenant_valid", "emission_norm", ["tenant_id", "valid_until"])


def downgrade() -> None:
    op.drop_index("ix_emission_norm_tenant_valid", table_name="emission_norm")
    op.drop_index("ix_emission_norm_source_id", table_name="emission_norm")
    op.drop_table("emission_norm")
    op.drop_index("ix_emission_source_facility_id", table_name="emission_source")
    op.drop_table("emission_source")
