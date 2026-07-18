"""cmt02: committee proceedings — attendance, votes, meeting protocol snapshot.

Additive (P10-01 срез-2, TZ B.17). Adds:
- enum votechoice + committee_decision_vote
- committee_meeting_attendance
- committee_meeting: held_at, protocol_seq/year, members_total, present_count, quorum_met
- partial unique index on protocol number (per committee/year)

Chains off rb01. Honest downgrade drops in reverse (child→parent) order.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260714_cmt02_committee_proceedings"
down_revision = "20260710_rb01_report_definition"
branch_labels = None
depends_on = None

_VOTE_CHOICE = postgresql.ENUM("for", "against", "abstain", name="votechoice", create_type=False)


def _common(*extra: sa.Column) -> list[sa.Column]:
    return [
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
        *extra,
    ]


def upgrade() -> None:
    bind = op.get_bind()
    _VOTE_CHOICE.create(bind, checkfirst=True)

    op.add_column(
        "committee_meeting", sa.Column("held_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("committee_meeting", sa.Column("protocol_seq", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("protocol_year", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("members_total", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("present_count", sa.Integer(), nullable=True))
    op.add_column("committee_meeting", sa.Column("quorum_met", sa.Boolean(), nullable=True))
    op.create_index(
        "uq_committee_protocol_no",
        "committee_meeting",
        ["tenant_id", "committee_id", "protocol_year", "protocol_seq"],
        unique=True,
        postgresql_where=sa.text("protocol_seq IS NOT NULL"),
    )

    op.create_table(
        "committee_meeting_attendance",
        *_common(
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
            sa.Column("present", sa.Boolean(), nullable=False, server_default=sa.true()),
        ),
        sa.UniqueConstraint("tenant_id", "meeting_id", "person_id", name="uq_committee_attendance"),
    )
    op.create_table(
        "committee_decision_vote",
        *_common(
            sa.Column(
                "decision_id",
                sa.String(length=36),
                sa.ForeignKey("committee_decision.id", ondelete="CASCADE"),
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
            sa.Column("choice", _VOTE_CHOICE, nullable=False),
        ),
        sa.UniqueConstraint("tenant_id", "decision_id", "person_id", name="uq_committee_vote"),
    )


def downgrade() -> None:
    op.drop_table("committee_decision_vote")
    op.drop_table("committee_meeting_attendance")
    op.drop_index("uq_committee_protocol_no", table_name="committee_meeting")
    for col in (
        "quorum_met",
        "present_count",
        "members_total",
        "protocol_year",
        "protocol_seq",
        "held_at",
    ):
        op.drop_column("committee_meeting", col)
    bind = op.get_bind()
    _VOTE_CHOICE.drop(bind, checkfirst=True)
