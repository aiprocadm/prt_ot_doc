"""rs03: карточки водителей (разд. 56.2, срез-2).

Вторая предметная таблица контура БДД. Человек НЕ дублируется: карточка
ссылается на ядрового ``person`` и добавляет только водительское —
удостоверение, категории, стаж и допуск к управлению. Второй список
сотрудников разошёлся бы с первым на первой же кадровой правке.

Один человек — одна карточка (``uq_driver_person``), один номер удостоверения
— одна карточка (``uq_driver_license``): дубль это ошибка ввода, а не второй
водитель. Обе уникальности стоят В БАЗЕ, а не только в проверке ручки.

``license_due`` NULLABLE, и пустая дата означает «СВЕДЕНИЙ НЕТ», а не
«бессрочно»: у водительского удостоверения бессрочности не бывает — тот же
довод, что у полиса и диагностической карты в rs01.

СТАЖ ХРАНИТСЯ ДАТОЙ (``experience_since``), а не числом лет: число молча
устаревает, и отличить устаревшее от верного нельзя.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модель наследует VersionedMixin
(канон br01).

Revision ID: 20260829_rs03_drivers
Revises: 20260828_rs02_road_safety_grant
Create Date: 2026-08-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260829_rs03_drivers"
down_revision = "20260828_rs02_road_safety_grant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "road_driver",
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
            "person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id"),
            nullable=False,
        ),
        sa.Column("license_number", sa.String(length=32), nullable=False),
        sa.Column("categories", sa.JSON(), nullable=False),
        sa.Column("license_issued_at", sa.Date(), nullable=True),
        sa.Column("license_due", sa.Date(), nullable=True),
        sa.Column("experience_since", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="admitted"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "person_id", name="uq_driver_person"),
        sa.UniqueConstraint("tenant_id", "license_number", name="uq_driver_license"),
    )
    op.create_index("ix_road_driver_person_id", "road_driver", ["person_id"])
    op.create_index("ix_driver_tenant_status", "road_driver", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_driver_tenant_status", table_name="road_driver")
    op.drop_index("ix_road_driver_person_id", table_name="road_driver")
    op.drop_table("road_driver")
