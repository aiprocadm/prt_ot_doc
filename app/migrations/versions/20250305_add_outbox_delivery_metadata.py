"""Add outbox delivery metadata

Revision ID: 20250305_add_outbox_delivery_metadata
Revises: 20250218_ot_hazards_workplaces, 8d2c1a6c5e24
Create Date: 2025-03-05 00:00:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20250305_add_outbox_delivery_metadata"
down_revision: tuple[str, str] = (
    "20250218_ot_hazards_workplaces",
    "8d2c1a6c5e24",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("outbox", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "attempts",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )
        batch.add_column(sa.Column("last_error", sa.String(length=512), nullable=True))
        batch.create_index("ix_outbox_processed_at", ["processed_at"], unique=False)
        batch.alter_column("attempts", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("outbox", schema=None) as batch:
        batch.drop_index("ix_outbox_processed_at")
        batch.drop_column("last_error")
        batch.drop_column("attempts")
