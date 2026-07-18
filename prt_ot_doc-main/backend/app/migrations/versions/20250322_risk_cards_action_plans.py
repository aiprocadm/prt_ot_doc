"""Add risk assessment artifacts tables.

Revision ID: 20250322_risk_cards_action_plans
Revises: 20250321_outbox_dedupe_key
Create Date: 2025-03-22 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20250322_risk_cards_action_plans"
down_revision: str | tuple[str, ...] = "20250321_outbox_dedupe_key"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("riskmethodology", schema=None) as batch:
        batch.add_column(sa.Column("code", sa.String(length=64), nullable=True))
        batch.create_unique_constraint("uq_risk_methodology_code", ["tenant_id", "code"])

    op.execute(
        sa.text(
            "UPDATE riskmethodology SET code = LOWER(REPLACE(name, ' ', '_')) WHERE code IS NULL"
        )
    )

    with op.batch_alter_table("riskmethodology", schema=None) as batch:
        batch.alter_column("code", nullable=False)

    with op.batch_alter_table("risk_hazards", schema=None) as batch:
        batch.add_column(
            sa.Column("recommended_measures", sa.JSON(), nullable=False, server_default="[]")
        )

    with op.batch_alter_table("risk_assessments", schema=None) as batch:
        batch.add_column(
            sa.Column("assessment_key", sa.String(length=64), nullable=True)
        )
        batch.add_column(
            sa.Column("assessment_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("methodology_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("methodology_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("workplace_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("employee_id", sa.String(length=36), nullable=True))
        batch.create_index(
            "ix_risk_assessments_methodology_id", ["methodology_id"], unique=False
        )
        batch.create_index("ix_risk_assessments_workplace_id", ["workplace_id"], unique=False)
        batch.create_index("ix_risk_assessments_employee_id", ["employee_id"], unique=False)
        batch.create_unique_constraint(
            "uq_risk_assessment_version",
            ["tenant_id", "assessment_key", "assessment_version"],
        )
        batch.create_foreign_key(
            "fk_risk_assessments_methodology",
            "riskmethodology",
            ["methodology_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_risk_assessments_workplace",
            "workplace",
            ["workplace_id"],
            ["id"],
        )
        batch.create_foreign_key(
            "fk_risk_assessments_employee",
            "person",
            ["employee_id"],
            ["id"],
        )

    op.execute(
        sa.text(
            "UPDATE risk_assessments SET assessment_key = id WHERE assessment_key IS NULL"
        )
    )

    with op.batch_alter_table("risk_assessments", schema=None) as batch:
        batch.alter_column("assessment_key", nullable=False)
        batch.alter_column("assessment_version", server_default=None)

    op.create_table(
        "risk_assessment_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("hazard_id", sa.String(length=36), nullable=False),
        sa.Column("probability", sa.Integer(), nullable=False),
        sa.Column("severity", sa.Integer(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("methodology_id", sa.String(length=36), nullable=True),
        sa.Column("methodology_version", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hazard_id"], ["risk_hazards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["methodology_id"], ["riskmethodology.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_risk_assessment_items_tenant_id",
        "risk_assessment_items",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_risk_assessment_items_assessment_id",
        "risk_assessment_items",
        ["assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_risk_assessment_items_hazard_id",
        "risk_assessment_items",
        ["hazard_id"],
        unique=False,
    )
    op.create_index(
        "ix_risk_assessment_items_methodology_id",
        "risk_assessment_items",
        ["methodology_id"],
        unique=False,
    )
    op.create_index(
        "ix_risk_assessment_items_tenant_assessment",
        "risk_assessment_items",
        ["tenant_id", "assessment_id"],
        unique=False,
    )

    op.create_table(
        "risk_cards",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("workplace_id", sa.String(length=36), nullable=True),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("employee_id", sa.String(length=36), nullable=True),
        sa.Column("methodology_id", sa.String(length=36), nullable=True),
        sa.Column("methodology_version", sa.Integer(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"]),
        sa.ForeignKeyConstraint(["workplace_id"], ["workplace.id"]),
        sa.ForeignKeyConstraint(["position_id"], ["position.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["methodology_id"], ["riskmethodology.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_risk_cards_tenant_id", "risk_cards", ["tenant_id"], unique=False)
    op.create_index(
        "ix_risk_cards_assessment_id", "risk_cards", ["assessment_id"], unique=False
    )
    op.create_index(
        "ix_risk_cards_methodology_id", "risk_cards", ["methodology_id"], unique=False
    )
    op.create_index(
        "ix_risk_cards_tenant_assessment",
        "risk_cards",
        ["tenant_id", "assessment_id"],
        unique=False,
    )

    op.create_table(
        "action_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("workplace_id", sa.String(length=36), nullable=True),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("employee_id", sa.String(length=36), nullable=True),
        sa.Column("methodology_id", sa.String(length=36), nullable=True),
        sa.Column("methodology_version", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
        sa.ForeignKeyConstraint(["assessment_id"], ["risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"]),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"]),
        sa.ForeignKeyConstraint(["workplace_id"], ["workplace.id"]),
        sa.ForeignKeyConstraint(["position_id"], ["position.id"]),
        sa.ForeignKeyConstraint(["employee_id"], ["person.id"]),
        sa.ForeignKeyConstraint(["methodology_id"], ["riskmethodology.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_plans_tenant_id", "action_plans", ["tenant_id"], unique=False)
    op.create_index(
        "ix_action_plans_assessment_id", "action_plans", ["assessment_id"], unique=False
    )
    op.create_index(
        "ix_action_plans_methodology_id", "action_plans", ["methodology_id"], unique=False
    )
    op.create_index(
        "ix_action_plans_tenant_assessment",
        "action_plans",
        ["tenant_id", "assessment_id"],
        unique=False,
    )

    op.create_table(
        "action_plan_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("plan_id", sa.String(length=36), nullable=False),
        sa.Column("assessment_id", sa.String(length=36), nullable=False),
        sa.Column("hazard_id", sa.String(length=36), nullable=True),
        sa.Column("measure_text", sa.Text(), nullable=False),
        sa.Column("owner_role", sa.String(length=64), nullable=True),
        sa.Column("owner_id", sa.String(length=64), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="planned"),
        sa.Column("methodology_id", sa.String(length=36), nullable=True),
        sa.Column("methodology_version", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["assessment_id"], ["risk_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["hazard_id"], ["risk_hazards.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["methodology_id"], ["riskmethodology.id"]),
        sa.ForeignKeyConstraint(["plan_id"], ["action_plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_plan_items_tenant_id",
        "action_plan_items",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_action_plan_items_plan_id",
        "action_plan_items",
        ["plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_action_plan_items_assessment_id",
        "action_plan_items",
        ["assessment_id"],
        unique=False,
    )
    op.create_index(
        "ix_action_plan_items_hazard_id",
        "action_plan_items",
        ["hazard_id"],
        unique=False,
    )
    op.create_index(
        "ix_action_plan_items_methodology_id",
        "action_plan_items",
        ["methodology_id"],
        unique=False,
    )
    op.create_index(
        "ix_action_plan_items_tenant_plan",
        "action_plan_items",
        ["tenant_id", "plan_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_action_plan_items_tenant_plan", table_name="action_plan_items")
    op.drop_index("ix_action_plan_items_methodology_id", table_name="action_plan_items")
    op.drop_index("ix_action_plan_items_hazard_id", table_name="action_plan_items")
    op.drop_index("ix_action_plan_items_assessment_id", table_name="action_plan_items")
    op.drop_index("ix_action_plan_items_plan_id", table_name="action_plan_items")
    op.drop_index("ix_action_plan_items_tenant_id", table_name="action_plan_items")
    op.drop_table("action_plan_items")

    op.drop_index("ix_action_plans_tenant_assessment", table_name="action_plans")
    op.drop_index("ix_action_plans_methodology_id", table_name="action_plans")
    op.drop_index("ix_action_plans_assessment_id", table_name="action_plans")
    op.drop_index("ix_action_plans_tenant_id", table_name="action_plans")
    op.drop_table("action_plans")

    op.drop_index("ix_risk_cards_tenant_assessment", table_name="risk_cards")
    op.drop_index("ix_risk_cards_methodology_id", table_name="risk_cards")
    op.drop_index("ix_risk_cards_assessment_id", table_name="risk_cards")
    op.drop_index("ix_risk_cards_tenant_id", table_name="risk_cards")
    op.drop_table("risk_cards")

    op.drop_index("ix_risk_assessment_items_tenant_assessment", table_name="risk_assessment_items")
    op.drop_index("ix_risk_assessment_items_methodology_id", table_name="risk_assessment_items")
    op.drop_index("ix_risk_assessment_items_hazard_id", table_name="risk_assessment_items")
    op.drop_index("ix_risk_assessment_items_assessment_id", table_name="risk_assessment_items")
    op.drop_index("ix_risk_assessment_items_tenant_id", table_name="risk_assessment_items")
    op.drop_table("risk_assessment_items")

    with op.batch_alter_table("risk_assessments", schema=None) as batch:
        batch.drop_constraint("fk_risk_assessments_employee", type_="foreignkey")
        batch.drop_constraint("fk_risk_assessments_workplace", type_="foreignkey")
        batch.drop_constraint("fk_risk_assessments_methodology", type_="foreignkey")
        batch.drop_constraint("uq_risk_assessment_version", type_="unique")
        batch.drop_index("ix_risk_assessments_employee_id")
        batch.drop_index("ix_risk_assessments_workplace_id")
        batch.drop_index("ix_risk_assessments_methodology_id")
        batch.drop_column("employee_id")
        batch.drop_column("workplace_id")
        batch.drop_column("methodology_version")
        batch.drop_column("methodology_id")
        batch.drop_column("assessment_version")
        batch.drop_column("assessment_key")

    with op.batch_alter_table("risk_hazards", schema=None) as batch:
        batch.drop_column("recommended_measures")

    with op.batch_alter_table("riskmethodology", schema=None) as batch:
        batch.drop_constraint("uq_risk_methodology_code", type_="unique")
        batch.drop_column("code")
