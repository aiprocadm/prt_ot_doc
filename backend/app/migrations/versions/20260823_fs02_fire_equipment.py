"""fs02: первичные средства и системы защиты ПБ (Доп. №1 разд. 54.1).

Первая СОБСТВЕННАЯ таблица контура пожарной безопасности: огнетушители,
краны, щиты и системы (АУПС/АУПТ/СОУЭ) с регламентными сроками перезарядки и
поверки — то, чего нет у общих сущностей ядра и что первым смотрит инспектор.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK на site допустим: это create_table, а не add_column к
существующей таблице (класс граблей wa02 сюда не относится).

Revision ID: 20260823_fs02_fire_equipment
Revises: 20260822_gc01_company_parent_id
Create Date: 2026-08-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260823_fs02_fire_equipment"
down_revision = "20260822_gc01_company_parent_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fire_safety_equipment",
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
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("recharge_due", sa.Date(), nullable=True),
        sa.Column("inspection_due", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fire_safety_equipment_site_id", "fire_safety_equipment", ["site_id"])
    op.create_index("ix_fire_equipment_tenant_kind", "fire_safety_equipment", ["tenant_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_fire_equipment_tenant_kind", table_name="fire_safety_equipment")
    op.drop_index("ix_fire_safety_equipment_site_id", table_name="fire_safety_equipment")
    op.drop_table("fire_safety_equipment")
