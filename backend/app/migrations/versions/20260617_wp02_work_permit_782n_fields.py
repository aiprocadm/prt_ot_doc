"""wp02: descriptive 782н fields on work_permit (additive).

8 nullable columns for the official «работа на высоте» form sections.
VARCHAR/TEXT/JSON, no native enums. Table name LITERAL (AST-audit blindspot).
Honest downgrade drops exactly the added columns.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260617_wp02_work_permit_782n_fields"
down_revision = "20260616_wp01_work_permit_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_permit", sa.Column("subdivision_text", sa.String(length=255), nullable=True))
    op.add_column("work_permit", sa.Column("content_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("conditions_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("safety_systems", sa.JSON(), nullable=True))
    op.add_column("work_permit", sa.Column("measures_before_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("measures_during_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("special_conditions_text", sa.Text(), nullable=True))
    op.add_column("work_permit", sa.Column("ppe_text", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("work_permit", "ppe_text")
    op.drop_column("work_permit", "special_conditions_text")
    op.drop_column("work_permit", "measures_during_text")
    op.drop_column("work_permit", "measures_before_text")
    op.drop_column("work_permit", "safety_systems")
    op.drop_column("work_permit", "conditions_text")
    op.drop_column("work_permit", "content_text")
    op.drop_column("work_permit", "subdivision_text")
