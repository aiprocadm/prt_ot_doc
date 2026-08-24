"""fs04: журнал регламентных работ по средствам ПБ (Доп. №1 разд. 54.1).

ТО систем, поверки, испытания (пожарные лестницы, водопровод) и устранение
замечаний. До этой таблицы у средства хранился только СЛЕДУЮЩИЙ срок, и
отметить выполненную работу можно было единственным способом — затереть срок;
от самой работы не оставалось следа.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK на fire_safety_equipment допустим: это create_table, а не
add_column к существующей таблице (класс граблей wa02 сюда не относится).
Колонка ``version`` обязательна — модель наследует VersionedMixin (канон br01).

Revision ID: 20260824_fs04_fire_maintenance
Revises: 20260824_sec65_rls_fire_drill
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260824_fs04_fire_maintenance"
down_revision = "20260824_sec65_rls_fire_drill"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fire_maintenance",
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
            "equipment_id",
            sa.String(length=36),
            sa.ForeignKey("fire_safety_equipment.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=False),
        sa.Column("performer", sa.String(length=255), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_due", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fire_maintenance_equipment_id", "fire_maintenance", ["equipment_id"])
    op.create_index(
        "ix_fire_maintenance_tenant_performed",
        "fire_maintenance",
        ["tenant_id", "performed_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_fire_maintenance_tenant_performed", table_name="fire_maintenance")
    op.drop_index("ix_fire_maintenance_equipment_id", table_name="fire_maintenance")
    op.drop_table("fire_maintenance")
