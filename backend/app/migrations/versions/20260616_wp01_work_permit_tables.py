"""wp01: work-permit (наряд-допуск) tables — document + members + events.

Additive: three new tables. VARCHAR vocabularies (status/work_type/role/event_type),
no native enums (анти-грабли enum-parity). FKs to existing site/person/file/work_permit.
Names are LITERAL (AST-audit blindspot). Round-trip-safe: downgrade drops children
before the parent.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260616_wp01_work_permit_tables"
down_revision = "20260615_prm01_permit_status_varchar"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    ]


def upgrade() -> None:
    op.create_table(
        "work_permit",
        *_base_columns(),
        sa.Column("number", sa.String(length=64), nullable=True),
        sa.Column("work_type", sa.String(length=32), nullable=False),
        sa.Column("zone_text", sa.String(length=255), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("equipment_text", sa.Text(), nullable=True),
        sa.Column("hazards_text", sa.Text(), nullable=True),
        sa.Column("measures_text", sa.Text(), nullable=True),
        sa.Column("planned_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("suspended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "number", name="uq_work_permit_tenant_number"),
    )
    op.create_index("ix_work_permit_status", "work_permit", ["tenant_id", "status"])
    op.create_index("ix_work_permit_site", "work_permit", ["tenant_id", "site_id"])

    op.create_table(
        "work_permit_member",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "tenant_id", "work_permit_id", "person_id", "role", name="uq_work_permit_member"
        ),
    )
    op.create_index("ix_work_permit_member_permit", "work_permit_member", ["work_permit_id"])
    op.create_index("ix_work_permit_member_person", "work_permit_member", ["person_id"])

    op.create_table(
        "work_permit_event",
        *_base_columns(),
        sa.Column("work_permit_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("photo_file_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["work_permit_id"], ["work_permit.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["photo_file_id"], ["file.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_work_permit_event_permit", "work_permit_event", ["work_permit_id"])


def downgrade() -> None:
    op.drop_table("work_permit_event")
    op.drop_table("work_permit_member")
    op.drop_table("work_permit")
