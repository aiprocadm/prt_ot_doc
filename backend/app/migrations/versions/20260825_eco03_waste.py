"""eco03: паспорта отходов и журнал учёта движения (Доп. №1 разд. 55.2).

Паспорт отхода I–IV класса (пятый класс паспортизации не подлежит) с кодом
ФККО и годовым лимитом из НООЛР/декларации, и записи журнала учёта: что, когда,
сколько и кому передано.

Договор с оператором НЕ дублируется — ссылка на ядровой ``contract``.

Уникальность (арендатор, код ФККО) — на уровне БД: два паспорта на один код это
один вид отхода, заведённый дважды, и учёт по нему стал бы враньём.

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260825_eco03_waste
Revises: 20260825_eco02_ecology_grant
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260825_eco03_waste"
down_revision = "20260825_eco02_ecology_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "waste_passport",
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
            sa.ForeignKey("nvos_facility.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("fkko_code", sa.String(length=16), nullable=False),
        sa.Column("hazard_class", sa.String(length=8), nullable=False),
        sa.Column("approved_on", sa.Date(), nullable=True),
        sa.Column("annual_limit_tons", sa.Numeric(14, 3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "fkko_code", name="uq_waste_passport_fkko"),
    )
    op.create_index("ix_waste_passport_facility_id", "waste_passport", ["facility_id"])

    op.create_table(
        "waste_movement",
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
            "passport_id",
            sa.String(length=36),
            sa.ForeignKey("waste_passport.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("happened_on", sa.Date(), nullable=False),
        sa.Column("quantity_tons", sa.Numeric(14, 3), nullable=False),
        sa.Column("contract_id", sa.String(length=36), sa.ForeignKey("contract.id"), nullable=True),
        sa.Column("counterparty", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_waste_movement_passport_id", "waste_movement", ["passport_id"])
    op.create_index("ix_waste_movement_tenant_date", "waste_movement", ["tenant_id", "happened_on"])


def downgrade() -> None:
    op.drop_index("ix_waste_movement_tenant_date", table_name="waste_movement")
    op.drop_index("ix_waste_movement_passport_id", table_name="waste_movement")
    op.drop_table("waste_movement")
    op.drop_index("ix_waste_passport_facility_id", table_name="waste_passport")
    op.drop_table("waste_passport")
