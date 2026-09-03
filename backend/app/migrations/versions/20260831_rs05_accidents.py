"""rs05: учёт ДТП (разд. 56.2, срез-4).

Четвёртая предметная таблица контура БДД и первая, которая тянется В ЯДРО:
``incident_id`` — НЕОБЯЗАТЕЛЬНАЯ ссылка на ядровое расследование.

ПОЧЕМУ НЕ РАЗМЕТКА ЯДРОВОГО ИНЦИДЕНТА. Ядровой ``incident`` требует площадку
(``site_id`` NOT NULL), а ДТП происходит на дороге, где площадки нет; вид
инцидента — перечисление в базе, общее для всего продукта; и главное, помятый
бампер это ДТП, но не происшествие по охране труда. Поэтому здесь СВОЯ
таблица со связью, а не поглощение чужой.

``ondelete=SET NULL`` у ссылки на инцидент: удаление расследования не должно
уносить с собой факт ДТП — это разные вещи.

Водитель НЕОБЯЗАТЕЛЕН: в стоящую машину въезжают и без водителя за рулём.

Мероприятия своей таблицей НЕ заводятся: ядровой ``corrective_actions``
адресуется парой ``source_type`` + ``source_id`` и принимает любую строку.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модель наследует VersionedMixin
(канон br01).

Revision ID: 20260831_rs05_accidents
Revises: 20260830_sec65_rls_waybills
Create Date: 2026-08-31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260831_rs05_accidents"
down_revision = "20260830_sec65_rls_waybills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "road_accident",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("place", sa.String(length=255), nullable=False),
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
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("injured_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fatalities_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "fault",
            sa.String(length=24),
            nullable=False,
            server_default="not_established",
        ),
        sa.Column("gibdd_reference", sa.String(length=128), nullable=True),
        sa.Column(
            "incident_id",
            sa.String(length=36),
            sa.ForeignKey("incident.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_road_accident_vehicle_id", "road_accident", ["vehicle_id"])
    op.create_index("ix_road_accident_driver_id", "road_accident", ["driver_id"])
    op.create_index("ix_road_accident_incident_id", "road_accident", ["incident_id"])
    op.create_index(
        "ix_accident_tenant_occurred", "road_accident", ["tenant_id", "occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_accident_tenant_occurred", table_name="road_accident")
    op.drop_index("ix_road_accident_incident_id", table_name="road_accident")
    op.drop_index("ix_road_accident_driver_id", table_name="road_accident")
    op.drop_index("ix_road_accident_vehicle_id", table_name="road_accident")
    op.drop_table("road_accident")
