"""Hotfix: allow lowercase active in templateversionstatus enum.

Revision ID: 20260407_hotfix_templateversionstatus_active
Revises: 20260406_next61_analytics_read_models
Create Date: 2026-04-07
"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260407_hotfix_templateversionstatus_active"
down_revision = "20260406_next61_analytics_read_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE templateversionstatus ADD VALUE IF NOT EXISTS 'active'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely without recreating the type.
    pass
