"""fs03: тренировки и учения по ПБ (Доп. №1 разд. 54.1).

План-график тренировок по эвакуации, протокол проведения и анализ. До этой
таблицы дисциплина умела выпустить программу тренировки документом, но не
умела её учесть — «контроль сроков» по тренировкам был невыполним.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK на site допустим: это create_table, а не add_column к
существующей таблице (класс граблей wa02 сюда не относится). Колонка
``version`` обязательна — модель наследует VersionedMixin (канон br01).

Revision ID: 20260824_fs03_fire_drill
Revises: 20260823_sec65_rls_fire_equipment
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260824_fs03_fire_drill"
down_revision = "20260823_sec65_rls_fire_equipment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fire_drill",
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
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("planned_on", sa.Date(), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=True),
        sa.Column("scenario", sa.Text(), nullable=True),
        sa.Column("participants", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fire_drill_site_id", "fire_drill", ["site_id"])
    op.create_index("ix_fire_drill_tenant_planned", "fire_drill", ["tenant_id", "planned_on"])


def downgrade() -> None:
    op.drop_index("ix_fire_drill_tenant_planned", table_name="fire_drill")
    op.drop_index("ix_fire_drill_site_id", table_name="fire_drill")
    op.drop_table("fire_drill")
