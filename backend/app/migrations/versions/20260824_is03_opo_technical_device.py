"""is03: технические устройства ОПО и ЭПБ (Доп. №1 разд. 54.2).

Учёт технических устройств с назначенным сроком службы и заключением
экспертизы промышленной безопасности. Ядровые ``asset``/``equipment`` для
этого не годятся: две и три колонки, без единой ручки API и без единого поля
срока — учитывать по ним экспертизу нечем.

Привязка к ``hazardous_facility``, а не к площадке: экспертиза и надзор идут
по зарегистрированному объекту, а объектов на площадке бывает несколько.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK допустим: это create_table, а не add_column к существующей
таблице (класс граблей wa02 сюда не относится). Колонка ``version``
обязательна — модель наследует VersionedMixin (канон br01).

Revision ID: 20260824_is03_opo_device
Revises: 20260824_is02_opo_module_grant
Create Date: 2026-08-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260824_is03_opo_device"
down_revision = "20260824_is02_opo_module_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opo_technical_device",
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
            sa.ForeignKey("hazardous_facility.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("serial_number", sa.String(length=64), nullable=True),
        sa.Column("commissioned_on", sa.Date(), nullable=True),
        sa.Column("lifetime_until", sa.Date(), nullable=True),
        sa.Column("epb_conclusion_number", sa.String(length=64), nullable=True),
        sa.Column("epb_registered_on", sa.Date(), nullable=True),
        sa.Column("epb_valid_until", sa.Date(), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="in_operation",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_opo_technical_device_facility_id", "opo_technical_device", ["facility_id"]
    )
    op.create_index(
        "ix_opo_device_tenant_epb",
        "opo_technical_device",
        ["tenant_id", "epb_valid_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_opo_device_tenant_epb", table_name="opo_technical_device")
    op.drop_index("ix_opo_technical_device_facility_id", table_name="opo_technical_device")
    op.drop_table("opo_technical_device")
