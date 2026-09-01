"""rs06: учёт нарушений ПДД (разд. 56.2, срез-8).

Пятая предметная таблица контура БДД и последнее незакрытое в пункте
«Водители» (состав, стаж и категории дал rs03, режим труда и отдыха — rs04).

ПОЧЕМУ НЕ ЯДРОВОЕ ``violation``. Ядровое нарушение — находка ПРОВЕРКИ по
пункту чек-листа: ``inspection_id`` NOT NULL и ``clause_ref``. У нарушения ПДД
никакой проверки нет — оно приходит постановлением ГИБДД или снимается
камерой. Общее у них только слово.

``driver_id`` NULLABLE, И ЭТО НЕ НЕДОСМОТР: камера фиксирует ГОСНОМЕР, а не
человека. Постановление приходит собственнику, и кто был за рулём,
организация выясняет сама — иногда никогда. NOT NULL заставлял бы вписывать
наугад.

``vehicle_id`` NOT NULL: нарушение без своего ТС организации не касается.

``fine_amount`` NULLABLE, и пусто означает «штраф НЕ НАЛОЖЕН», а не «сумма
неизвестна»: у замечания собственного контроля штрафа не бывает.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модель наследует VersionedMixin
(канон br01).

Revision ID: 20260901_rs06_violations
Revises: 20260901_sec65_rls_internships
Create Date: 2026-09-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260901_rs06_violations"
down_revision = "20260901_sec65_rls_internships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "road_violation",
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
            "vehicle_id",
            sa.String(length=36),
            sa.ForeignKey("road_vehicle.id"),
            nullable=False,
        ),
        sa.Column(
            "driver_id",
            sa.String(length=36),
            sa.ForeignKey("road_driver.id"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source", sa.String(length=16), nullable=False, server_default="camera"
        ),
        sa.Column("article", sa.String(length=64), nullable=True),
        sa.Column("resolution_number", sa.String(length=64), nullable=True),
        sa.Column("place", sa.String(length=255), nullable=True),
        sa.Column("fine_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("fine_paid_on", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_road_violation_vehicle_id", "road_violation", ["vehicle_id"])
    op.create_index("ix_road_violation_driver_id", "road_violation", ["driver_id"])
    op.create_index(
        "ix_violation_tenant_occurred", "road_violation", ["tenant_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_violation_tenant_occurred", table_name="road_violation")
    op.drop_index("ix_road_violation_driver_id", table_name="road_violation")
    op.drop_index("ix_road_violation_vehicle_id", table_name="road_violation")
    op.drop_table("road_violation")
