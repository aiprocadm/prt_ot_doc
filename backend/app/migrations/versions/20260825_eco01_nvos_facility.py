"""eco01: реестр объектов НВОС (Доп. №1 разд. 55.1).

Первая СОБСТВЕННАЯ таблица контура экологии: постановка на государственный
учёт, категория I–IV, актуализация сведений. До неё по экологии не было ни
одной сущности — дисциплина существовала словарной строкой, а весь контент
сводился к комплекту документов, где всё вводится руками.

Уникальность (арендатор, код реестра) — на уровне БД: дубль означает объект,
заведённый дважды, и любой счёт по категориям стал бы враньём.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK на site допустим: это create_table, а не add_column к
существующей таблице (класс граблей wa02 сюда не относится). Колонка
``version`` обязательна — модель наследует VersionedMixin (канон br01).

Revision ID: 20260825_eco01_nvos_facility
Revises: 20260825_sec65_rls_pc
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260825_eco01_nvos_facility"
down_revision = "20260825_sec65_rls_pc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "nvos_facility",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("site_id", sa.String(length=36), sa.ForeignKey("site.id"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("register_number", sa.String(length=64), nullable=False),
        sa.Column("category", sa.String(length=8), nullable=False),
        sa.Column("registered_on", sa.Date(), nullable=True),
        sa.Column("actualized_on", sa.Date(), nullable=True),
        sa.Column("excluded_on", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="registered"
        ),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "register_number", name="uq_nvos_facility_register"
        ),
    )
    op.create_index("ix_nvos_facility_site_id", "nvos_facility", ["site_id"])
    op.create_index(
        "ix_nvos_facility_tenant_category", "nvos_facility", ["tenant_id", "category"]
    )


def downgrade() -> None:
    op.drop_index("ix_nvos_facility_tenant_category", table_name="nvos_facility")
    op.drop_index("ix_nvos_facility_site_id", table_name="nvos_facility")
    op.drop_table("nvos_facility")
