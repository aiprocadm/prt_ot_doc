"""wp06: type_specific JSON на work_permit (additive) — структурная секция вида работ.

Generic-колонка под per-type секции (ОЗП газоанализ/вентиляция и т.д.); высота
держит safety_systems и не трогается. Имя таблицы ЛИТЕРАЛОМ (AST-audit blindspot).
Honest downgrade удаляет колонку.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260621_wp06_work_permit_type_specific"
down_revision = "20260620_wp05_work_permit_closing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_permit", sa.Column("type_specific", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_permit", "type_specific")
