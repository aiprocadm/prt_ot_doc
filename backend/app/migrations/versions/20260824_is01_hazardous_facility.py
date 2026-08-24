"""is01: реестр опасных производственных объектов (Доп. №1 разд. 54.2).

Первая СОБСТВЕННАЯ таблица контура промышленной безопасности: идентификация,
регистрационный номер в госреестре и класс опасности I–IV. До неё «ОПО»
выражалось тремя полями площадки, причём класс опасности был свободной
строкой, перегруженной категорией пожарной опасности, — считать по классам
было нечего.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK на site допустим: это create_table, а не add_column к
существующей таблице (класс граблей wa02 сюда не относится). Колонка
``version`` обязательна — модель наследует VersionedMixin (канон br01).

Уникальность (tenant_id, register_number) — на уровне БД, а не только в
прикладной проверке: дубль госномера означает объект, заведённый дважды, и
любой счёт по классам стал бы враньём.

Revision ID: 20260824_is01_hazardous_facility
Revises: 20260824_sec65_rls_fire_doc
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260824_is01_hazardous_facility"
down_revision = "20260824_sec65_rls_fire_doc"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hazardous_facility",
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
        sa.Column("hazard_class", sa.String(length=8), nullable=False),
        sa.Column("registered_on", sa.Date(), nullable=True),
        sa.Column("excluded_on", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="registered",
        ),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "register_number", name="uq_hazardous_facility_register"
        ),
    )
    op.create_index("ix_hazardous_facility_site_id", "hazardous_facility", ["site_id"])
    op.create_index(
        "ix_hazardous_facility_tenant_class",
        "hazardous_facility",
        ["tenant_id", "hazard_class"],
    )


def downgrade() -> None:
    op.drop_index("ix_hazardous_facility_tenant_class", table_name="hazardous_facility")
    op.drop_index("ix_hazardous_facility_site_id", table_name="hazardous_facility")
    op.drop_table("hazardous_facility")
