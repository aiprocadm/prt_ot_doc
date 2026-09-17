"""rs01: реестр транспортных средств (разд. 56.2).

Первая предметная таблица контура БДД. До неё по разд. 56.2 не было ни одной
модели транспорта: ТЗ отсылало к «transport safety (vNext §17.3)», а в коде
были только словарная строка дисциплины, комплект документов BDD_BASE и запись
в библиотеке правил.

Государственный регистрационный знак уникален у арендатора: одна машина — одна
запись, второй такой же номер это ошибка ввода, а не второе ТС.

Сроки (диагностическая карта, полис, поверка тахографа) NULLABLE, и пустая
дата означает «СВЕДЕНИЙ НЕТ», а не «бессрочно» — у полиса и диагностической
карты бессрочности не бывает. Это ОТЛИЧИЕ от реестров документов ПБ и ГО, где
пустой срок означал именно бессрочность.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модель наследует VersionedMixin
(канон br01).

Revision ID: 20260828_rs01_vehicles
Revises: 20260827_cd06_training_discipline
Create Date: 2026-08-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260828_rs01_vehicles"
down_revision = "20260827_cd06_training_discipline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "road_vehicle",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("plate_number", sa.String(length=32), nullable=False),
        sa.Column("brand_model", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="in_service"),
        sa.Column("vin", sa.String(length=32), nullable=True),
        sa.Column("year_made", sa.Integer(), nullable=True),
        sa.Column("site_id", sa.String(length=36), sa.ForeignKey("site.id"), nullable=True),
        sa.Column("inspection_due", sa.Date(), nullable=True),
        sa.Column("insurance_due", sa.Date(), nullable=True),
        sa.Column("license_number", sa.String(length=128), nullable=True),
        sa.Column("license_due", sa.Date(), nullable=True),
        sa.Column(
            "tachograph_installed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("tachograph_due", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "plate_number", name="uq_vehicle_plate"),
    )
    op.create_index("ix_road_vehicle_site_id", "road_vehicle", ["site_id"])
    op.create_index("ix_vehicle_tenant_status", "road_vehicle", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_vehicle_tenant_status", table_name="road_vehicle")
    op.drop_index("ix_road_vehicle_site_id", table_name="road_vehicle")
    op.drop_table("road_vehicle")
