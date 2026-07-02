"""wa05: additive ppeitem.min_stock column (P10-06 min-stock threshold).

Revision ID: 20260703_wa05_ppeitem_min_stock
Revises: 20260702_wa04_ppe_stock_movement
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260703_wa05_ppeitem_min_stock"
down_revision = "20260702_wa04_ppe_stock_movement"
branch_labels = None
depends_on = None


def upgrade() -> None:
    col = sa.Column("min_stock", sa.Integer(), nullable=False, server_default="0")
    op.add_column("ppeitem", col)


def downgrade() -> None:
    op.drop_column("ppeitem", "min_stock")
