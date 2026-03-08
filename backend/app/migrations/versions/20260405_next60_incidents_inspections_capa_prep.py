"""next60 incidents inspections capa prep domains"""

from alembic import op
import sqlalchemy as sa

revision = "20260405_next60_incidents_inspections_capa_prep"
down_revision = "20260401_next58_safety_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "incident_cases",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("workplace_id", sa.String(length=36), nullable=True),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("contractor_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("incident_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("consequences", sa.Text(), nullable=True),
        sa.Column("root_cause_summary", sa.Text(), nullable=True),
        sa.Column("external_report_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("linked_risk_review_required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_incident_cases_tenant_code"),
    )
    op.create_index("ix_incident_cases_tenant_site_status_severity_occurred", "incident_cases", ["tenant_id", "site_id", "status", "severity", "occurred_at"], unique=False)
    op.create_table(
        "incident_persons",
        sa.Column("incident_case_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("fio_text", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["incident_case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_incident_persons_incident_case_id"), "incident_persons", ["incident_case_id"], unique=False)
    op.create_table(
        "incident_investigations",
        sa.Column("incident_case_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("methodology", sa.Text(), nullable=True),
        sa.Column("findings_json", sa.JSON(), nullable=True),
        sa.Column("causes_json", sa.JSON(), nullable=True),
        sa.Column("recommendations_json", sa.JSON(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["incident_case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_case_id"),
    )

    op.create_table(
        "inspection_plans",
        sa.Column("code", sa.Text(), nullable=False), sa.Column("name", sa.Text(), nullable=False), sa.Column("plan_type", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True), sa.Column("period_end", sa.Date(), nullable=True), sa.Column("status", sa.Text(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True), sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id")
    )
    op.create_table("inspection_plan_items", sa.Column("inspection_plan_id", sa.String(length=36), nullable=False), sa.Column("site_id", sa.String(length=36), nullable=True), sa.Column("department_id", sa.String(length=36), nullable=True), sa.Column("contractor_id", sa.String(length=36), nullable=True), sa.Column("planned_for", sa.Date(), nullable=False), sa.Column("subject", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False), sa.Column("tenant_id", sa.String(length=36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False), sa.Column("id", sa.String(length=36), nullable=False), sa.ForeignKeyConstraint(["department_id"], ["department.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["inspection_plan_id"], ["inspection_plans.id"], ondelete="CASCADE"), sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"), sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id"))
    op.create_index(op.f("ix_inspection_plan_items_inspection_plan_id"), "inspection_plan_items", ["inspection_plan_id"], unique=False)

    for name in ["ops_inspections", "findings", "ops_prescriptions", "prescription_items", "corrective_actions", "inspection_prep_packages", "inspection_prep_items", "inspection_prep_gaps"]:
        op.create_table(name, sa.Column("id", sa.String(length=36), primary_key=True, nullable=False), sa.Column("tenant_id", sa.String(length=36), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("version", sa.Integer(), nullable=False))


def downgrade() -> None:
    for name in ["inspection_prep_gaps", "inspection_prep_items", "inspection_prep_packages", "corrective_actions", "prescription_items", "ops_prescriptions", "findings", "ops_inspections", "inspection_plan_items", "inspection_plans", "incident_investigations", "incident_persons", "incident_cases"]:
        op.drop_table(name)
