"""prescription lifecycle: evidence + closed_at cols + verified enum value

TZ-3.4-V12-01 / W-A item #2. Additive. Adds two nullable columns to
inspection_prescription and extends the prescriptionstatus PG enum with
'verified'. No data backfill.

The new enum value is NOT used (no UPDATE/cast) in this migration, so the
single ALTER TYPE ADD VALUE is transaction-safe on PG12+ — mirrors the
precedent in 20260328_next55_templates_lifecycle. SQLite has no enum type
(the column behaves as TEXT) and the test harness builds schema from ORM
metadata, so no SQLite DDL is needed here.

Chains off the W-A head 20260530_wa02_featureenablement_drop_feature_fk. The
repo runs ``alembic upgrade heads`` (plural — many heads by design); this
additive change applies regardless of the other parallel branches.

Revision ID: 20260530_wa03_prescription_lifecycle
Revises: 20260530_wa02_featureenablement_drop_feature_fk
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260530_wa03_prescription_lifecycle"
down_revision = "20260530_wa02_featureenablement_drop_feature_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inspection_prescription", sa.Column("evidence", sa.Text(), nullable=True))
    op.add_column(
        "inspection_prescription",
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE prescriptionstatus ADD VALUE IF NOT EXISTS 'verified'")


def downgrade() -> None:
    op.drop_column("inspection_prescription", "closed_at")
    op.drop_column("inspection_prescription", "evidence")
    # The 'verified' enum value is intentionally NOT removed: Postgres cannot
    # DROP a value from an enum type without recreating it (documented one-way,
    # matching repo precedent for in-place enum extensions).
