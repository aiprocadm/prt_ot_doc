"""cmt01: committees срез-1 — 6 tables (additive, P10-01 / TZ B.17).

committee / committee_member / committee_meeting / committee_agenda_item /
committee_decision / committee_decision_task. Native enums созданы с .value
лейблами (enum-pg-label-parity). Honest downgrade удаляет таблицы и enum-типы
в обратном (child→parent) порядке.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260625_cmt01_committees"
down_revision = "20260623_cm01_company_status_tags_person_position"
branch_labels = None
depends_on = None


_COMMITTEE_KIND = postgresql.ENUM(
    "osms",
    "pb",
    "commission_training",
    "commission_investigation",
    "other",
    name="committeekind",
    create_type=False,
)
_MEMBER_ROLE = postgresql.ENUM(
    "chair", "secretary", "member", name="committeememberrole", create_type=False
)
_MEETING_STATUS = postgresql.ENUM(
    "planned", "held", "cancelled", name="meetingstatus", create_type=False
)
_TASK_STATUS = postgresql.ENUM(
    "open", "in_progress", "done", name="decisiontaskstatus", create_type=False
)


def _common(*extra: sa.Column) -> list[sa.Column]:
    """id + tenant base + timestamps + version columns shared by every table."""
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
    for enum_type in (_COMMITTEE_KIND, _MEMBER_ROLE, _MEETING_STATUS, _TASK_STATUS):
        enum_type.create(bind, checkfirst=True)

    op.create_table(
        "committee",
        *_common(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("kind", _COMMITTEE_KIND, nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        ),
    )
    op.create_table(
        "committee_member",
        *_common(
            sa.Column(
                "committee_id",
                sa.String(length=36),
                sa.ForeignKey("committee.id", ondelete="CASCADE"),
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
            sa.Column("role", _MEMBER_ROLE, nullable=False),
        ),
        sa.UniqueConstraint(
            "tenant_id", "committee_id", "person_id", "role", name="uq_committee_member"
        ),
    )
    op.create_table(
        "committee_meeting",
        *_common(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "committee_id",
                sa.String(length=36),
                sa.ForeignKey("committee.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("location", sa.String(length=255), nullable=True),
            sa.Column("status", _MEETING_STATUS, nullable=False, server_default="planned"),
        ),
    )
    op.create_table(
        "committee_agenda_item",
        *_common(
            sa.Column(
                "meeting_id",
                sa.String(length=36),
                sa.ForeignKey("committee_meeting.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("seq", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("title", sa.String(length=500), nullable=False),
            sa.Column(
                "presenter_person_id",
                sa.String(length=36),
                sa.ForeignKey("person.id", ondelete="SET NULL"),
                nullable=True,
            ),
        ),
    )
    op.create_table(
        "committee_decision",
        *_common(
            sa.Column(
                "meeting_id",
                sa.String(length=36),
                sa.ForeignKey("committee_meeting.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "agenda_item_id",
                sa.String(length=36),
                sa.ForeignKey("committee_agenda_item.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        ),
    )
    op.create_table(
        "committee_decision_task",
        *_common(
            sa.Column(
                "decision_id",
                sa.String(length=36),
                sa.ForeignKey("committee_decision.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column(
                "assignee_person_id",
                sa.String(length=36),
                sa.ForeignKey("person.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("due_date", sa.Date(), nullable=True),
            sa.Column("status", _TASK_STATUS, nullable=False, server_default="open"),
            sa.Column("evidence_note", sa.Text(), nullable=True),
        ),
    )


def downgrade() -> None:
    op.drop_table("committee_decision_task")
    op.drop_table("committee_decision")
    op.drop_table("committee_agenda_item")
    op.drop_table("committee_meeting")
    op.drop_table("committee_member")
    op.drop_table("committee")
    bind = op.get_bind()
    for enum_type in (_TASK_STATUS, _MEETING_STATUS, _MEMBER_ROLE, _COMMITTEE_KIND):
        enum_type.drop(bind, checkfirst=True)
