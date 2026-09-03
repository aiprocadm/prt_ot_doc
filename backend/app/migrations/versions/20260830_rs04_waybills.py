"""rs04: путевые листы и отметки контроля (разд. 56.2, срез-3).

Третья предметная таблица контура БДД и первая, которая СВЯЗЫВАЕТ две
предыдущие: лист ссылается на ``road_vehicle`` и ``road_driver`` внешними
ключами, а не хранит номер машины и фамилию строками — строка «Иванов» не
связалась бы с карточкой допуска, и вопрос «выпускали ли отстранённого» остался
бы без ответа.

Три отметки контроля (предрейсовый медосмотр, послерейсовый медосмотр,
предрейсовый техконтроль) — КОЛОНКИ ОДНОГО ЛИСТА, а не три параллельные
таблицы: в жизни их ставят на одном документе, и разнесённые списки пришлось
бы сшивать по времени и фамилии.

Каждая отметка — строка из закрытого словаря с ТРЕМЯ значениями, а не булев
флажок: ``not_recorded`` (сведений нет) и ``failed`` (не пройден) — разные
факты, и склеивать их флажком значило бы потерять различие между дырой в
учёте и нарушением выпуска. server_default — ``not_recorded``: свежий лист не
считается ни пройденным, ни проваленным.

``uq_waybill_number`` стоит В БАЗЕ, а не только в проверке ручки. Индекс по
(tenant_id, issued_on) — под журнал за период: реестр листов растёт каждую
смену, в отличие от парка и водительского состава.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модель наследует VersionedMixin
(канон br01).

Revision ID: 20260830_rs04_waybills
Revises: 20260829_sec65_rls_drivers
Create Date: 2026-08-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260830_rs04_waybills"
down_revision = "20260829_sec65_rls_drivers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "road_waybill",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("number", sa.String(length=32), nullable=False),
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
            nullable=False,
        ),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("departure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("return_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "pre_trip_medical",
            sa.String(length=16),
            nullable=False,
            server_default="not_recorded",
        ),
        sa.Column(
            "post_trip_medical",
            sa.String(length=16),
            nullable=False,
            server_default="not_recorded",
        ),
        sa.Column(
            "pre_trip_technical",
            sa.String(length=16),
            nullable=False,
            server_default="not_recorded",
        ),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="issued"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "number", name="uq_waybill_number"),
    )
    op.create_index("ix_road_waybill_vehicle_id", "road_waybill", ["vehicle_id"])
    op.create_index("ix_road_waybill_driver_id", "road_waybill", ["driver_id"])
    op.create_index(
        "ix_waybill_tenant_issued", "road_waybill", ["tenant_id", "issued_on"]
    )


def downgrade() -> None:
    op.drop_index("ix_waybill_tenant_issued", table_name="road_waybill")
    op.drop_index("ix_road_waybill_driver_id", table_name="road_waybill")
    op.drop_index("ix_road_waybill_vehicle_id", table_name="road_waybill")
    op.drop_table("road_waybill")
