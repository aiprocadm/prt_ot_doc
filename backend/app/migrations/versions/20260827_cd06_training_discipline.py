"""cd06: дисциплина учебной программы (Доп. №1 разд. 56.1 + кросс-контур).

До этой колонки курс «Курсовое обучение по ГО» был НЕОТЛИЧИМ от курса по
охране труда: у ``training_course`` есть название, код, длительность и срок
действия, но нет отнесения к дисциплине. Вопрос требования 56.1 «какие
программы обучения по ГО заведены» не имел ответа в данных.

Дыра КРОСС-ДИСЦИПЛИНАРНАЯ: ровно так же неотличимы пожарно-технический
минимум, обучение по обращению с отходами и подготовка по промбезопасности —
поэтому размечается сам курс, а контуры дисциплин показывают свою часть.

Колонка NULLABLE: пусто означает «не размечено», а НЕ «общая охрана труда».
Backfill НЕ делается намеренно — приписать существующим курсам дисциплину по
названию значило бы выдумать данные, которых нет.

Additive-шаг (expand, правило OPS-74 разд. 74.2 по построению).

Revision ID: 20260827_cd06_training_discipline
Revises: 20260827_sec65_rls_cd_planning
Create Date: 2026-08-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260827_cd06_training_discipline"
down_revision = "20260827_sec65_rls_cd_planning"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "training_course",
        sa.Column("discipline", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_training_course_discipline",
        "training_course",
        ["tenant_id", "discipline"],
    )


def downgrade() -> None:
    op.drop_index("ix_training_course_discipline", table_name="training_course")
    op.drop_column("training_course", "discipline")
