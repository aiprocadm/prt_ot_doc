"""Add risk assessment action plan payloads.

Revision ID: 20250320_risk_assessment_action_plan
Revises: 20250318_pack_item_template_version
Create Date: 2025-03-20 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20250320_risk_assessment_action_plan"
down_revision: str | tuple[str, ...] = "20250318_pack_item_template_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_assessments", sa.Column("action_plan", sa.JSON(), nullable=True))
    op.add_column("risk_assessments", sa.Column("risk_card", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("risk_assessments", "risk_card")
    op.drop_column("risk_assessments", "action_plan")
