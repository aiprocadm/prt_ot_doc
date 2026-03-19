"""Add custom risk methodology enum value.

Revision ID: 20260318_next67_risk_custom_enum_hotfix
Revises: 20260318_next67
Create Date: 2026-03-18 18:30:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260318_next67_risk_custom_enum_hotfix"
down_revision = "20260318_next67"
branch_labels = None
depends_on = None



def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE riskmethodologytype ADD VALUE IF NOT EXISTS 'custom'")



def downgrade() -> None:
    # PostgreSQL enum values are not removed in-place safely.
    pass
