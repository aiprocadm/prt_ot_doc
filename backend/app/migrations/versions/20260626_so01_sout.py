"""so01: СОУТ срез-1 — 4 tables (additive, P10-04 / TZ B.10).

sout_campaign / sout_workplace / sout_factor / sout_guarantee. Native enums
созданы с .value лейблами (enum-pg-label-parity). ``soutclass`` backs two
columns (workplace.assessed_class + factor.measured_class) и создаётся ОДИН раз.
Honest downgrade удаляет таблицы и enum-типы в обратном (child→parent) порядке.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260626_so01_sout"
down_revision = "20260625_cmt01_committees"
branch_labels = None
depends_on = None


_CAMPAIGN_STATUS = postgresql.ENUM(
    "planned",
    "in_progress",
    "completed",
    "declared",
    "cancelled",
    name="soutcampaignstatus",
    create_type=False,
)
_SOUT_CLASS = postgresql.ENUM(
    "optimal",
    "acceptable",
    "harmful_3_1",
    "harmful_3_2",
    "harmful_3_3",
    "harmful_3_4",
    "dangerous",
    name="soutclass",
    create_type=False,
)
_GUARANTEE_KIND = postgresql.ENUM(
    "additional_leave",
    "extra_pay",
    "reduced_hours",
    "milk",
    "early_pension",
    "medical_exam",
    name="soutguaranteekind",
    create_type=False,
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
    for enum_type in (_CAMPAIGN_STATUS, _SOUT_CLASS, _GUARANTEE_KIND):
        enum_type.create(bind, checkfirst=True)

    # ``soutclass`` already created above; reference it without re-emitting DDL.
    sout_class_ref = sa.Enum(
        "optimal",
        "acceptable",
        "harmful_3_1",
        "harmful_3_2",
        "harmful_3_3",
        "harmful_3_4",
        "dangerous",
        name="soutclass",
        create_type=False,
    )

    op.create_table(
        "sout_campaign",
        *_common(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("expert_org_name", sa.String(length=255), nullable=True),
            sa.Column("report_number", sa.String(length=100), nullable=True),
            sa.Column("report_date", sa.Date(), nullable=True),
            sa.Column("status", _CAMPAIGN_STATUS, nullable=False, server_default="planned"),
            sa.Column("planned_date", sa.Date(), nullable=True),
            sa.Column("completed_date", sa.Date(), nullable=True),
        ),
    )
    op.create_table(
        "sout_workplace",
        *_common(
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "campaign_id",
                sa.String(length=36),
                sa.ForeignKey("sout_campaign.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("workplace_code", sa.String(length=100), nullable=False),
            sa.Column("position_name", sa.String(length=255), nullable=False),
            sa.Column(
                "person_id",
                sa.String(length=36),
                sa.ForeignKey("person.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("assessed_class", sout_class_ref, nullable=True),
            sa.Column("assessment_date", sa.Date(), nullable=True),
            sa.Column("next_assessment_date", sa.Date(), nullable=True),
        ),
    )
    op.create_table(
        "sout_factor",
        *_common(
            sa.Column(
                "workplace_id",
                sa.String(length=36),
                sa.ForeignKey("sout_workplace.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("code", sa.String(length=50), nullable=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("measured_class", sout_class_ref, nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
        ),
    )
    op.create_table(
        "sout_guarantee",
        *_common(
            sa.Column(
                "workplace_id",
                sa.String(length=36),
                sa.ForeignKey("sout_workplace.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("kind", _GUARANTEE_KIND, nullable=False),
            sa.Column("detail", sa.Text(), nullable=True),
        ),
    )


def downgrade() -> None:
    op.drop_table("sout_guarantee")
    op.drop_table("sout_factor")
    op.drop_table("sout_workplace")
    op.drop_table("sout_campaign")
    bind = op.get_bind()
    for enum_type in (_GUARANTEE_KIND, _SOUT_CLASS, _CAMPAIGN_STATUS):
        enum_type.drop(bind, checkfirst=True)
