"""rb01: report-builder — saved report definitions (P10-07 §24.3).

Additive. One new tenant-scoped table. VARCHAR/JSON only, no FKs beyond tenant_id.
Round-trip-safe: downgrade drops the table. Table/column names are LITERAL
(AST-audit blindspot).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260710_rb01_report_definition"
down_revision = "20260709_med03_psychiatric_342n"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "report_definition",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("dataset_code", sa.String(length=64), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("is_system", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_report_definition_tenant_name"),
    )


def downgrade() -> None:
    op.drop_table("report_definition")
