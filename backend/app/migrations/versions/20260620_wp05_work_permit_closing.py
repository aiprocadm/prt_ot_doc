"""wp05: closing (Ф3b) — completion-act columns on work_permit (additive).

Закрытие 1:1 с нарядом → поля на work_permit, без новой таблицы. Подписи
закрытия живут в signature_requests (object_type="work_permit_closing").
Имена таблиц ЛИТЕРАЛОМ (AST-audit blindspot). Honest downgrade удаляет колонки.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260620_wp05_work_permit_closing"
down_revision = "20260618_wp04_work_permit_ops_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_permit", sa.Column("completion_text", sa.Text(), nullable=True))
    op.add_column(
        "work_permit",
        sa.Column("completion_recorded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("work_permit", "completion_recorded_at")
    op.drop_column("work_permit", "completion_text")
