"""wp03: целевой инструктаж наряда-допуска (Ф2) — таблица work_permit_briefing.

Additive: одна новая таблица. FK→work_permit (CASCADE), FK→person (SET NULL).
Имена таблиц LITERAL (AST-audit blindspot). Honest downgrade drops the table.
Подписи отдельной таблицы НЕ получают — живут в signature_requests (Подход A).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260618_wp03_work_permit_briefing"
down_revision = "20260617_wp02_work_permit_782n_fields"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    op.create_table(
        "work_permit_briefing",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("conducted_by_person_id", sa.String(length=36), nullable=True),
        sa.Column("conducted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("topics_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conducted_by_person_id"], ["person.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_work_permit_briefing_permit", "work_permit_briefing", ["work_permit_id"])


def downgrade() -> None:
    op.drop_table("work_permit_briefing")
