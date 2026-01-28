"""Add outbox dedupe key

Revision ID: 20250321_outbox_dedupe_key
Revises: 20250320_risk_assessment_action_plan
Create Date: 2025-03-21 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20250321_outbox_dedupe_key"
down_revision: str | tuple[str, ...] = "20250320_risk_assessment_action_plan"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("outbox", schema=None) as batch:
        batch.add_column(sa.Column("dedupe_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint(
            "uq_outbox_dedupe", ["tenant_id", "event_type", "dedupe_key"]
        )


def downgrade() -> None:
    with op.batch_alter_table("outbox", schema=None) as batch:
        batch.drop_constraint("uq_outbox_dedupe", type_="unique")
        batch.drop_column("dedupe_key")
