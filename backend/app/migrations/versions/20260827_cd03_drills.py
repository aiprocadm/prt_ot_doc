"""cd03: учения и тренировки ГО (разд. 56.1).

План-график с протоколом и анализом. Своя таблица, а не переиспользование
``fire_drill``: у учения ГО есть то, чего у пожарной тренировки не бывает —
задействованное ФОРМИРОВАНИЕ (cd01), а виды отличаются основанием,
участниками и органом.

Формирование НЕОБЯЗАТЕЛЬНО (``formation_id`` nullable): объектовая тренировка
проводится всем персоналом, а не силами звена.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модель наследует VersionedMixin
(канон br01).

Revision ID: 20260827_cd03_drills
Revises: 20260827_cd02_civil_defense_grant
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260827_cd03_drills"
down_revision = "20260827_cd02_civil_defense_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cd_drill",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("planned_on", sa.Date(), nullable=False),
        sa.Column("held_on", sa.Date(), nullable=True),
        sa.Column(
            "formation_id",
            sa.String(length=36),
            sa.ForeignKey("cd_formation.id"),
            nullable=True,
        ),
        sa.Column(
            "site_id", sa.String(length=36), sa.ForeignKey("site.id"), nullable=True
        ),
        sa.Column("scenario", sa.Text(), nullable=True),
        sa.Column("participants", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("findings", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cd_drill_formation_id", "cd_drill", ["formation_id"])
    op.create_index("ix_cd_drill_site_id", "cd_drill", ["site_id"])
    op.create_index("ix_cd_drill_tenant_planned", "cd_drill", ["tenant_id", "planned_on"])


def downgrade() -> None:
    op.drop_index("ix_cd_drill_tenant_planned", table_name="cd_drill")
    op.drop_index("ix_cd_drill_site_id", table_name="cd_drill")
    op.drop_index("ix_cd_drill_formation_id", table_name="cd_drill")
    op.drop_table("cd_drill")
