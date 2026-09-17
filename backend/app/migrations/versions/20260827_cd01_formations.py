"""cd01: нештатные формирования ГО и ЧС с составами (разд. 56.1).

Первые предметные таблицы контура ГО и ЧС: формирование (НАСФ/НФГО, закрытый
вид из двух по ФЗ-28) и строка состава, ссылающаяся на человека ЯДРА (принцип
мультидисциплинарности — «бойцов» дисциплина не заводит).

Две уникальности НА УРОВНЕ БД, обе осмысленные:

* название формирования уникально в организации: два «звена пожаротушения»
  без уточнения — ошибка ввода, а не два формирования;
* одна строка на пару «формирование + человек»: повторное включение
  выведенного сбрасывает дату вывода, а не плодит дубли.

Новые таблицы — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модели наследуют VersionedMixin
(канон br01).

Revision ID: 20260827_cd01_formations
Revises: 20260826_sec65_rls_fee
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260827_cd01_formations"
down_revision = "20260826_sec65_rls_fee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cd_formation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("purpose", sa.String(length=255), nullable=True),
        sa.Column(
            "commander_person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id"),
            nullable=True,
        ),
        sa.Column("equipment_notes", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "name", name="uq_cd_formation_name"),
    )

    op.create_table(
        "cd_formation_member",
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
            "formation_id",
            sa.String(length=36),
            sa.ForeignKey("cd_formation.id"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id"),
            nullable=False,
        ),
        sa.Column("role_in_formation", sa.String(length=128), nullable=True),
        sa.Column("assigned_on", sa.Date(), nullable=True),
        sa.Column("released_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "formation_id", "person_id", name="uq_cd_member_person"),
    )
    op.create_index("ix_cd_formation_member_formation_id", "cd_formation_member", ["formation_id"])
    op.create_index("ix_cd_formation_member_person_id", "cd_formation_member", ["person_id"])


def downgrade() -> None:
    op.drop_index("ix_cd_formation_member_person_id", table_name="cd_formation_member")
    op.drop_index("ix_cd_formation_member_formation_id", table_name="cd_formation_member")
    op.drop_table("cd_formation_member")
    op.drop_table("cd_formation")
