"""next60 incidents inspections capa prep domains"""

from alembic import op
import sqlalchemy as sa

revision = "20260405_next60_incidents_inspections_capa_prep"
down_revision = "20260401_next58_safety_core"
branch_labels = None
depends_on = None


def _base_cols(with_deleted: bool = True) -> list[sa.Column]:
    cols: list[sa.Column] = [
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    ]
    if with_deleted:
        cols.insert(0, sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    return cols


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
        * _base_cols(with_deleted=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_incident_cases_tenant_code"),
    )
    op.create_index(
        "ix_incident_cases_tenant_site_status_severity_occurred",
        "incident_cases",
        ["tenant_id", "site_id", "status", "severity", "occurred_at"],
        unique=False,
    )

    op.create_table(
        "incident_persons",
        sa.Column("incident_case_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("fio_text", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["incident_case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
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
        *_base_cols(with_deleted=True),
        sa.ForeignKeyConstraint(["incident_case_id"], ["incident_cases.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("incident_case_id"),
    )

    op.create_table(
        "incident_attachments",
        sa.Column("incident_case_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("attachment_type", sa.Text(), nullable=False),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["incident_case_id"], ["incident_cases.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_incident_attachments_incident_case_id"), "incident_attachments", ["incident_case_id"], unique=False)

    op.create_table(
        "inspection_plans",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("plan_type", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        *_base_cols(with_deleted=True),
    )

    op.create_table(
        "inspection_plan_items",
        sa.Column("inspection_plan_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("contractor_id", sa.String(length=36), nullable=True),
        sa.Column("planned_for", sa.Date(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inspection_plan_id"], ["inspection_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
    )
    op.create_index(op.f("ix_inspection_plan_items_inspection_plan_id"), "inspection_plan_items", ["inspection_plan_id"], unique=False)

    op.create_table(
        "ops_inspections",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("plan_item_id", sa.String(length=36), nullable=True),
        sa.Column("inspection_type", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("contractor_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("inspector_user_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        *_base_cols(with_deleted=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["plan_item_id"], ["inspection_plan_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_ops_inspections_tenant_code"),
    )
    op.create_index(
        "ix_ops_inspections_tenant_site_status_type_started",
        "ops_inspections",
        ["tenant_id", "site_id", "status", "inspection_type", "started_at"],
        unique=False,
    )

    op.create_table(
        "inspection_checklists",
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("checklist_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_base_cols(with_deleted=True),
    )
    op.create_table(
        "inspection_checklist_items",
        sa.Column("inspection_checklist_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("section", sa.Text(), nullable=True),
        sa.Column("item_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("normative_ref", sa.Text(), nullable=True),
        sa.Column("severity_if_failed", sa.Text(), nullable=True),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["inspection_checklist_id"], ["inspection_checklists.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_inspection_checklist_items_inspection_checklist_id"), "inspection_checklist_items", ["inspection_checklist_id"], unique=False)

    op.create_table(
        "inspection_runs",
        sa.Column("inspection_id", sa.String(length=36), nullable=False),
        sa.Column("inspection_checklist_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["inspection_checklist_id"], ["inspection_checklists.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inspection_id"], ["ops_inspections.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_inspection_runs_inspection_id"), "inspection_runs", ["inspection_id"], unique=False)

    op.create_table(
        "inspection_run_items",
        sa.Column("inspection_run_id", sa.String(length=36), nullable=False),
        sa.Column("checklist_item_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("evidence_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["checklist_item_id"], ["inspection_checklist_items.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["inspection_run_id"], ["inspection_runs.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_inspection_run_items_inspection_run_id"), "inspection_run_items", ["inspection_run_id"], unique=False)

    op.create_table(
        "inspection_attachments",
        sa.Column("inspection_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("attachment_type", sa.Text(), nullable=False),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["inspection_id"], ["ops_inspections.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_inspection_attachments_inspection_id"), "inspection_attachments", ["inspection_id"], unique=False)

    op.create_table(
        "findings",
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("workplace_id", sa.String(length=36), nullable=True),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("risk_map_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("finding_type", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        *_base_cols(with_deleted=True),
        sa.ForeignKeyConstraint(["department_id"], ["department.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_findings_tenant_source_status_severity", "findings", ["tenant_id", "source_type", "source_id", "status", "severity"], unique=False)

    op.create_table(
        "ops_prescriptions",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("issuer_name", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        *_base_cols(with_deleted=True),
        sa.UniqueConstraint("tenant_id", "code", name="uq_ops_prescriptions_tenant_code"),
    )
    op.create_index("ix_ops_prescriptions_tenant_status_due", "ops_prescriptions", ["tenant_id", "status", "due_date"], unique=False)

    op.create_table(
        "prescription_items",
        sa.Column("prescription_id", sa.String(length=36), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=True),
        sa.Column("item_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("responsible_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        *_base_cols(with_deleted=True),
        sa.ForeignKeyConstraint(["finding_id"], ["findings.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["prescription_id"], ["ops_prescriptions.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_prescription_items_prescription_id"), "prescription_items", ["prescription_id"], unique=False)

    op.create_table(
        "corrective_actions",
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("action_type", sa.Text(), nullable=False),
        sa.Column("responsible_user_id", sa.String(length=36), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_comment", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("effectiveness_status", sa.Text(), nullable=True),
        *_base_cols(with_deleted=True),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_corrective_actions_tenant_responsible_status_due", "corrective_actions", ["tenant_id", "responsible_user_id", "status", "due_date"], unique=False)

    op.create_table(
        "corrective_action_attachments",
        sa.Column("corrective_action_id", sa.String(length=36), nullable=False),
        sa.Column("file_id", sa.String(length=36), nullable=False),
        sa.Column("attachment_type", sa.Text(), nullable=False),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["corrective_action_id"], ["corrective_actions.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_corrective_action_attachments_corrective_action_id"), "corrective_action_attachments", ["corrective_action_id"], unique=False)

    op.create_table(
        "inspection_prep_packages",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("contractor_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("package_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("target_inspection_date", sa.Date(), nullable=True),
        sa.Column("source_inspection_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_cols(with_deleted=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_inspection_id"], ["ops_inspections.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_inspection_prep_packages_tenant_code"),
    )
    op.create_index("ix_inspection_prep_packages_tenant_site_status_target", "inspection_prep_packages", ["tenant_id", "site_id", "status", "target_inspection_date"], unique=False)

    op.create_table(
        "inspection_prep_items",
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("item_type", sa.Text(), nullable=False),
        sa.Column("reference_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["package_id"], ["inspection_prep_packages.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_inspection_prep_items_package_id"), "inspection_prep_items", ["package_id"], unique=False)

    op.create_table(
        "inspection_prep_gaps",
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("gap_type", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=True),
        sa.Column("entity_id", sa.String(length=36), nullable=True),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("corrective_action_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        *_base_cols(with_deleted=False),
        sa.ForeignKeyConstraint(["corrective_action_id"], ["corrective_actions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["package_id"], ["inspection_prep_packages.id"], ondelete="CASCADE"),
    )
    op.create_index(op.f("ix_inspection_prep_gaps_package_id"), "inspection_prep_gaps", ["package_id"], unique=False)


def downgrade() -> None:
    for table in [
        "inspection_prep_gaps",
        "inspection_prep_items",
        "inspection_prep_packages",
        "corrective_action_attachments",
        "corrective_actions",
        "prescription_items",
        "ops_prescriptions",
        "findings",
        "inspection_attachments",
        "inspection_run_items",
        "inspection_runs",
        "inspection_checklist_items",
        "inspection_checklists",
        "ops_inspections",
        "inspection_plan_items",
        "inspection_plans",
        "incident_attachments",
        "incident_investigations",
        "incident_persons",
        "incident_cases",
    ]:
        op.drop_table(table)
