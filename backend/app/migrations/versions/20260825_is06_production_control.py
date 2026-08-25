"""is06: производственный контроль на ОПО (Доп. №1 разд. 54.2).

План ПК — годовой документ организации, эксплуатирующей ОПО, с ответственным за
осуществление производственного контроля; мероприятия плана — его пункты с
разделом, сроком, ответственным и результатом. В коде не было ничего: поиск по
``production_control`` давал единственное попадание — подпись поля в комплекте
документов по отходам.

Уникальность (арендатор, год) — на уровне БД: план ПК годовой, и второй план на
тот же год делает бессмысленным сам вопрос «есть ли план на 2026 год».

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260825_is06_production_control
Revises: 20260825_is05_attestation_area
Create Date: 2026-08-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260825_is06_production_control"
down_revision = "20260825_is05_attestation_area"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "opo_production_control_plan",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("approved_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "year", name="uq_pc_plan_year"),
    )
    op.create_table(
        "opo_production_control_measure",
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
            "plan_id",
            sa.String(length=36),
            sa.ForeignKey("opo_production_control_plan.id"),
            nullable=False,
        ),
        sa.Column("section", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("responsible", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="planned"),
        sa.Column("completed_on", sa.Date(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_opo_production_control_measure_plan_id",
        "opo_production_control_measure",
        ["plan_id"],
    )
    op.create_index(
        "ix_pc_measure_tenant_due",
        "opo_production_control_measure",
        ["tenant_id", "due_on"],
    )


def downgrade() -> None:
    op.drop_index("ix_pc_measure_tenant_due", table_name="opo_production_control_measure")
    op.drop_index(
        "ix_opo_production_control_measure_plan_id",
        table_name="opo_production_control_measure",
    )
    op.drop_table("opo_production_control_measure")
    op.drop_table("opo_production_control_plan")
