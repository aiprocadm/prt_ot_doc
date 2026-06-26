"""so03: СОУТ срез-3 — bridges to Position + RiskHazard (additive, P10-04 / TZ B.10).

Two nullable FK columns mirroring ``PPENorm`` shape so СОУТ rows can resolve to the
keys норм СИЗ/медосмотров use:
  * ``sout_workplace.position_id`` -> ``position.id`` (SET NULL)
  * ``sout_factor.hazard_id``      -> ``risk_hazards.id`` (SET NULL)

SET NULL (not CASCADE): deleting a position/hazard nulls the link but never erases
the СОУТ measurement row. Honest downgrade drops both columns. Table names literal
(audit-static-analysis lesson).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260626_so03_sout_norm_bridges"
down_revision = "20260626_so02_sout_class_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sout_workplace", sa.Column(
        "position_id",
        sa.String(length=36),
        sa.ForeignKey("position.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.create_index("ix_sout_workplace_position_id", "sout_workplace", ["position_id"])
    op.add_column("sout_factor", sa.Column(
        "hazard_id",
        sa.String(length=36),
        sa.ForeignKey("risk_hazards.id", ondelete="SET NULL"),
        nullable=True,
    ))
    op.create_index("ix_sout_factor_hazard_id", "sout_factor", ["hazard_id"])


def downgrade() -> None:
    op.drop_index("ix_sout_factor_hazard_id", table_name="sout_factor")
    op.drop_column("sout_factor", "hazard_id")
    op.drop_index("ix_sout_workplace_position_id", table_name="sout_workplace")
    op.drop_column("sout_workplace", "position_id")
