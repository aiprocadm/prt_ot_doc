"""is04: журнал работ по техническим устройствам ОПО (Доп. №1 разд. 54.2).

Диагностирование, освидетельствование, экспертиза промышленной безопасности,
ТО и ремонт. До этой таблицы у устройства были только СРОКИ и ни одной записи
о том, что с ним делали: отметить проведённую экспертизу можно было
единственным способом — затереть срок правкой поля.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). FK на opo_technical_device допустим: это create_table, а не
add_column к существующей таблице (класс граблей wa02 сюда не относится).
Колонка ``version`` обязательна — модель наследует VersionedMixin (канон br01).

Revision ID: 20260825_is04_opo_device_work
Revises: 20260824_sec65_rls_opo_dev
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260825_is04_opo_device_work"
down_revision = "20260824_sec65_rls_opo_dev"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opo_device_work",
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
            "device_id",
            sa.String(length=36),
            sa.ForeignKey("opo_technical_device.id"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("performed_on", sa.Date(), nullable=False),
        sa.Column("performer", sa.String(length=255), nullable=True),
        sa.Column("result", sa.String(length=32), nullable=False),
        sa.Column("conclusion_number", sa.String(length=64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_due", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_opo_device_work_device_id", "opo_device_work", ["device_id"])
    op.create_index(
        "ix_opo_device_work_tenant_performed",
        "opo_device_work",
        ["tenant_id", "performed_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_opo_device_work_tenant_performed", table_name="opo_device_work")
    op.drop_index("ix_opo_device_work_device_id", table_name="opo_device_work")
    op.drop_table("opo_device_work")
