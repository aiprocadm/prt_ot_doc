"""med03: 342н psychiatric assessment — activity-type catalog + position mapping + exam fields.

Additive. Two new tenant-scoped tables + two columns on medical_exam. VARCHAR-only, one FK to
position, JSON default '[]'. Round-trip-safe: downgrade drops columns then tables.
Table/column names are LITERAL (AST-audit blindspot).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260709_med03_psychiatric_342n"
down_revision = "20260709_wh01_webhook_delivery_outbox_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "psychiatric_activity_type",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="1825"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_psychiatric_activity_type_tenant_code"),
    )
    op.create_table(
        "psychiatric_position_activity",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("position_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("activity_code", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["position_id"], ["position.id"]),
        sa.UniqueConstraint(
            "tenant_id",
            "position_id",
            "activity_code",
            name="uq_psychiatric_position_activity",
        ),
    )
    op.add_column(
        "medical_exam",
        sa.Column("psychiatric_protocol_no", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "medical_exam",
        sa.Column(
            "psychiatric_activity_codes",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("medical_exam", "psychiatric_activity_codes")
    op.drop_column("medical_exam", "psychiatric_protocol_no")
    op.drop_table("psychiatric_position_activity")
    op.drop_table("psychiatric_activity_type")
