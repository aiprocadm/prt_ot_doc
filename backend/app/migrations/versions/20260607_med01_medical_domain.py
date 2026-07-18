"""med01: medical domain — extend medical_exam + norm/referral/suspension (TZ B.8).

Additive. New enum types are created explicitly on PG; dropped on downgrade after
their owning tables/columns (orphan-type lesson, PR #639).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260607_med01_medical_domain"
down_revision = "20260602_iter49_enum_label_parity"
branch_labels = None
depends_on = None

_EXAM_KIND = postgresql.ENUM(
    "periodic",
    "preliminary",
    "psychiatric",
    "fluorography",
    "health_book",
    name="medicalexamkind",
    create_type=False,
)
_FITNESS = postgresql.ENUM(
    "fit", "fit_with_restrictions", "unfit", name="medicalfitness", create_type=False
)
_REF_STATUS = postgresql.ENUM(
    "issued", "scheduled", "completed", "cancelled", name="medicalreferralstatus", create_type=False
)
_SUSP_STATUS = postgresql.ENUM(
    "active", "lifted", name="medicalsuspensionstatus", create_type=False
)
_SUSP_REASON = postgresql.ENUM(
    "unfit", "contraindication", name="medicalsuspensionreason", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum_type in (_EXAM_KIND, _FITNESS, _REF_STATUS, _SUSP_STATUS, _SUSP_REASON):
        enum_type.create(bind, checkfirst=True)

    op.add_column("medical_exam", sa.Column("exam_kind", _EXAM_KIND, nullable=True))
    op.add_column("medical_exam", sa.Column("fitness", _FITNESS, nullable=True))
    op.add_column("medical_exam", sa.Column("restrictions", sa.Text(), nullable=True))
    op.add_column(
        "medical_exam",
        sa.Column("contraindications", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column("medical_exam", sa.Column("referral_id", sa.String(length=36), nullable=True))
    op.add_column(
        "medical_exam", sa.Column("medical_org_name", sa.String(length=255), nullable=True)
    )
    op.create_index("ix_medical_exam_referral_id", "medical_exam", ["referral_id"])

    op.create_table(
        "medical_norm",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "position_id", sa.String(length=36), sa.ForeignKey("position.id"), nullable=False
        ),
        sa.Column(
            "hazard_id",
            sa.String(length=36),
            sa.ForeignKey("risk_hazards.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("exam_kind", _EXAM_KIND, nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("working_conditions_class", sa.String(length=32), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "position_id",
            "hazard_id",
            "exam_kind",
            name="uq_medical_norm_position_hazard_kind",
        ),
    )
    op.create_index("ix_medical_norm_position_id", "medical_norm", ["position_id"])
    op.create_index("ix_medical_norm_hazard_id", "medical_norm", ["hazard_id"])

    op.create_table(
        "medical_referral",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("exam_kind", _EXAM_KIND, nullable=False),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("status", _REF_STATUS, nullable=False, server_default="issued"),
        sa.Column("medical_org_name", sa.String(length=255), nullable=True),
        sa.Column(
            "issued_by",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "result_exam_id",
            sa.String(length=36),
            sa.ForeignKey("medical_exam.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_medical_referral_person_id", "medical_referral", ["person_id"])
    op.create_index("ix_medical_referral_due_at", "medical_referral", ["due_at"])
    op.create_index("ix_medical_referral_issued_by", "medical_referral", ["issued_by"])

    op.create_table(
        "medical_suspension",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id"), nullable=False),
        sa.Column("reason", _SUSP_REASON, nullable=False),
        sa.Column(
            "source_exam_id",
            sa.String(length=36),
            sa.ForeignKey("medical_exam.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", _SUSP_STATUS, nullable=False, server_default="active"),
        sa.Column(
            "lifted_by",
            sa.String(length=36),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_medical_suspension_person_id", "medical_suspension", ["person_id"])
    op.create_index("ix_medical_suspension_lifted_by", "medical_suspension", ["lifted_by"])

    # Columns above were added via bare op.add_column (ALTER TABLE ADD COLUMN —
    # SQLite-safe, committed before this block). batch_alter_table is used here
    # SOLELY to add the cyclic FK, which SQLite cannot express via ALTER TABLE.
    # Do NOT move the add_column calls inside this batch context.
    with op.batch_alter_table("medical_exam") as batch:
        batch.create_foreign_key(
            "fk_medical_exam_referral_id", "medical_referral", ["referral_id"], ["id"]
        )


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("medical_exam") as batch:
        batch.drop_constraint("fk_medical_exam_referral_id", type_="foreignkey")
    op.drop_index("ix_medical_suspension_lifted_by", table_name="medical_suspension")
    op.drop_index("ix_medical_suspension_person_id", table_name="medical_suspension")
    op.drop_table("medical_suspension")
    op.drop_index("ix_medical_referral_issued_by", table_name="medical_referral")
    op.drop_index("ix_medical_referral_due_at", table_name="medical_referral")
    op.drop_index("ix_medical_referral_person_id", table_name="medical_referral")
    op.drop_table("medical_referral")
    op.drop_index("ix_medical_norm_hazard_id", table_name="medical_norm")
    op.drop_index("ix_medical_norm_position_id", table_name="medical_norm")
    op.drop_table("medical_norm")
    op.drop_index("ix_medical_exam_referral_id", table_name="medical_exam")
    op.drop_column("medical_exam", "medical_org_name")
    op.drop_column("medical_exam", "referral_id")
    op.drop_column("medical_exam", "contraindications")
    op.drop_column("medical_exam", "restrictions")
    op.drop_column("medical_exam", "fitness")
    op.drop_column("medical_exam", "exam_kind")
    if bind.dialect.name == "postgresql":
        for type_name in (
            "medicalsuspensionreason",
            "medicalsuspensionstatus",
            "medicalreferralstatus",
            "medicalfitness",
            "medicalexamkind",
        ):
            op.execute(f"DROP TYPE IF EXISTS {type_name}")
