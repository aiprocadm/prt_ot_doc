"""cmt03: committee invitations + configurable quorum threshold.

Additive (P10-01 срез-4, TZ B.17). Adds:
- committee.quorum_threshold_pct (nullable int, NULL = строгое большинство)
- committee_meeting_invitation (приглашения на запланированное заседание)

Chains off ops71 import preview mode head. Honest downgrade.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260803_cmt03_committee_invitations_quorum"
down_revision = "20260730_ops71_import_preview_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("committee", sa.Column("quorum_threshold_pct", sa.Integer(), nullable=True))
    op.create_table(
        "committee_meeting_invitation",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.String(length=36),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "meeting_id",
            sa.String(length=36),
            sa.ForeignKey("committee_meeting.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "person_id",
            sa.String(length=36),
            sa.ForeignKey("person.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column("invited_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "meeting_id", "person_id", name="uq_committee_invitation"),
    )


def downgrade() -> None:
    op.drop_table("committee_meeting_invitation")
    op.drop_column("committee", "quorum_threshold_pct")
