"""wp04: ops-journal (Ф3a) — daily-admission table + event.meta column (additive).

New table work_permit_daily_admission (FK→work_permit CASCADE, FK→person SET NULL)
and a nullable JSON `meta` column on work_permit_event for structured extend /
crew-change details. Table names LITERAL (AST-audit blindspot). Honest downgrade
drops the column then the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260618_wp04_work_permit_ops_journal"
down_revision = "20260618_wp03_work_permit_briefing"
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
        "work_permit_daily_admission",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("admission_date", sa.Date(), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("admitted_by_person_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["admitted_by_person_id"], ["person.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_work_permit_daily_admission_permit",
        "work_permit_daily_admission",
        ["work_permit_id"],
    )
    op.add_column("work_permit_event", sa.Column("meta", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_permit_event", "meta")
    op.drop_table("work_permit_daily_admission")
