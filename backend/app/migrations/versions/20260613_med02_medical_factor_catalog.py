"""med02: 29н factor catalog (medical_factor) + RiskHazard.medical_factor_code (TZ B.8 §9.2).

Additive. New table + one nullable column on risk_hazards. VARCHAR category (no enum
types), no cross-base FK. Round-trip-safe: downgrade drops the column then the table.
Table/column names are LITERAL (AST-audit blindspot).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260613_med02_medical_factor_catalog"
down_revision = "20260612_ed03_briefing_signature_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "medical_factor",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False, server_default="factor"),
        sa.Column("exam_kinds", sa.JSON(), nullable=False),
        sa.Column("periodicity_months", sa.Integer(), nullable=False, server_default="12"),
        sa.Column("participants", sa.JSON(), nullable=True),
        sa.Column("lab_tests", sa.JSON(), nullable=True),
        sa.UniqueConstraint("tenant_id", "code", name="uq_medical_factor_tenant_code"),
    )
    op.add_column(
        "risk_hazards",
        sa.Column("medical_factor_code", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("risk_hazards", "medical_factor_code")
    op.drop_table("medical_factor")
