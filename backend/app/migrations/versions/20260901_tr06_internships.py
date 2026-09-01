"""tr06: стажировка на рабочем месте (ядро; требование разд. 56.2).

ПОЧЕМУ ТАБЛИЦА В ЯДРЕ, А НЕ В КОНТУРЕ БДД. Требование пришло из разд. 56.2
(«инструктажи и СТАЖИРОВКИ водителей»), но вещь не водительская: комплект
документов печатает «Стажировка: N смен» в первичном инструктаже НОВОГО
РАБОТНИКА, то есть по охране труда и любому рабочему. Своя таблица внутри БДД
означала бы второй реестр того же самого, как только понадобится стажировка
стропальщика.

Приём тот же, что у видов инструктажа (54.1), областей аттестации (54.2, 56.2)
и дисциплины курса (56.1): общая сущность + колонка ``discipline``. Контур
дисциплины отбирает СВОИ записи и копии не заводит.

``discipline`` NULLABLE: пусто означает «не размечено», а НЕ «общая охрана
труда» — приписывать записи принадлежность, которой в данных нет, нельзя.

Люди не дублируются: и стажёр, и наставник — ядровой ``person``. У наставника
``ondelete=SET NULL``: уволенный наставник не должен уносить с собой факт
стажировки.

Новая таблица — чисто additive-шаг (expand, правило OPS-74 разд. 74.2 по
построению). Колонка ``version`` обязательна — модель наследует VersionedMixin
(канон br01).

Revision ID: 20260901_tr06_internships
Revises: 20260831_sec65_rls_accidents
Create Date: 2026-09-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260901_tr06_internships"
down_revision = "20260831_sec65_rls_accidents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "internship",
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
            sa.ForeignKey("person.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mentor_person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("discipline", sa.String(length=32), nullable=True),
        sa.Column("subject", sa.String(length=255), nullable=True),
        sa.Column("planned_shifts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_shifts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_on", sa.Date(), nullable=True),
        sa.Column("finished_on", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="planned"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_internship_person_id", "internship", ["person_id"])
    op.create_index("ix_internship_mentor_person_id", "internship", ["mentor_person_id"])
    op.create_index("ix_internship_person", "internship", ["tenant_id", "person_id"])
    op.create_index(
        "ix_internship_discipline", "internship", ["tenant_id", "discipline"]
    )


def downgrade() -> None:
    op.drop_index("ix_internship_discipline", table_name="internship")
    op.drop_index("ix_internship_person", table_name="internship")
    op.drop_index("ix_internship_mentor_person_id", table_name="internship")
    op.drop_index("ix_internship_person_id", table_name="internship")
    op.drop_table("internship")
