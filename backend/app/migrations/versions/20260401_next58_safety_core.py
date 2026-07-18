"""next58 safety core org+risk+ppe

Revision ID: 20260401_next58
Revises: 20260330_next57_approval_sign_edo_orchestration
Create Date: 2026-04-01
"""

import sqlalchemy as sa
from alembic import op

revision = "20260401_next58"
down_revision = "20260330_next57"
branch_labels = None
depends_on = None


def _audit_cols() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("inn", sa.String(32), nullable=True),
        sa.Column("kpp", sa.String(32), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "sites",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "departments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("parent_id", sa.String(36), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        *_audit_cols(),
    )
    op.create_table(
        "positions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "workplaces",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id"), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("position_id", sa.String(36), sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("risk_class", sa.String(32), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "persons",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("company_id", sa.String(36), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id"), nullable=True),
        sa.Column("site_id", sa.String(36), sa.ForeignKey("sites.id"), nullable=True),
        sa.Column("workplace_id", sa.String(36), sa.ForeignKey("workplaces.id"), nullable=True),
        sa.Column("position_id", sa.String(36), sa.ForeignKey("positions.id"), nullable=True),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("middle_name", sa.String(100), nullable=True),
        sa.Column("tab_no", sa.String(32), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column("employment_status", sa.String(32), nullable=False),
        sa.Column("hired_at", sa.Date(), nullable=True),
        sa.Column("fired_at", sa.Date(), nullable=True),
        *_audit_cols(),
    )

    op.create_table(
        "risk_methodologies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("formula_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("scale_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        *_audit_cols(),
        sa.UniqueConstraint(
            "tenant_id", "code", "version_no", name="uq_risk_methodologies_code_version"
        ),
    )
    op.create_table(
        "hazards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("source_type", sa.String(32), nullable=True),
        sa.Column("severity_default", sa.Integer(), nullable=True),
        sa.Column("probability_default", sa.Integer(), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "risk_measures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("measure_type", sa.String(32), nullable=True),
        sa.Column("effectiveness_score", sa.Numeric(8, 2), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "hazard_measures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("hazard_id", sa.String(36), sa.ForeignKey("hazards.id"), nullable=False),
        sa.Column("measure_id", sa.String(36), sa.ForeignKey("risk_measures.id"), nullable=False),
        sa.Column("is_recommended", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "hazard_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("hazard_id", sa.String(36), sa.ForeignKey("hazards.id"), nullable=False),
        sa.Column("binding_type", sa.String(32), nullable=False),
        sa.Column("binding_id", sa.String(36), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "risk_maps",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.String(36), nullable=False),
        sa.Column(
            "risk_methodology_id",
            sa.String(36),
            sa.ForeignKey("risk_methodologies.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("created_by", sa.String(36), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "risk_map_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("risk_map_id", sa.String(36), sa.ForeignKey("risk_maps.id"), nullable=False),
        sa.Column("hazard_id", sa.String(36), sa.ForeignKey("hazards.id"), nullable=False),
        sa.Column("probability_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("severity_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("exposure_value", sa.Numeric(10, 2), nullable=True),
        sa.Column("raw_score", sa.Numeric(12, 2), nullable=True),
        sa.Column("risk_level", sa.String(16), nullable=True),
        sa.Column("residual_score", sa.Numeric(12, 2), nullable=True),
        sa.Column("residual_risk_level", sa.String(16), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "risk_map_item_measures",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column(
            "risk_map_item_id", sa.String(36), sa.ForeignKey("risk_map_items.id"), nullable=False
        ),
        sa.Column("measure_id", sa.String(36), sa.ForeignKey("risk_measures.id"), nullable=False),
        sa.Column("measure_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("effectiveness_comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "ppe_catalog",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("sku", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(64), nullable=True),
        sa.Column("size_grid_json", sa.JSON(), nullable=True),
        sa.Column("wear_term_months", sa.Integer(), nullable=True),
        sa.Column("certificate_no", sa.String(128), nullable=True),
        sa.Column("certificate_expiry", sa.Date(), nullable=True),
        sa.Column("unit", sa.String(16), nullable=False, server_default="pcs"),
        *_audit_cols(),
    )
    op.create_table(
        "ppe_norms",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("code", sa.String(64), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "ppe_norm_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("ppe_norm_id", sa.String(36), sa.ForeignKey("ppe_norms.id"), nullable=False),
        sa.Column("applies_to_type", sa.String(32), nullable=False),
        sa.Column("applies_to_id", sa.String(36), nullable=False),
        sa.Column("ppe_catalog_id", sa.String(36), sa.ForeignKey("ppe_catalog.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("period_months", sa.Integer(), nullable=True),
        sa.Column("size_required", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ppe_issues",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("person_id", sa.String(36), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("ppe_catalog_id", sa.String(36), sa.ForeignKey("ppe_catalog.id"), nullable=False),
        sa.Column("issue_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("size", sa.String(32), nullable=True),
        sa.Column("serial_no", sa.String(128), nullable=True),
        sa.Column("batch_no", sa.String(128), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_return_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("basis_text", sa.Text(), nullable=True),
        sa.Column(
            "related_norm_item_id", sa.String(36), sa.ForeignKey("ppe_norm_items.id"), nullable=True
        ),
        sa.Column("issued_by", sa.String(36), nullable=True),
        *_audit_cols(),
    )
    op.create_table(
        "ppe_personal_cards",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("person_id", sa.String(36), sa.ForeignKey("persons.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        *_audit_cols(),
        sa.UniqueConstraint("person_id", name="uq_ppe_personal_cards_person"),
    )
    op.create_table(
        "ppe_personal_card_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("tenant_id", sa.String(36), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column(
            "personal_card_id",
            sa.String(36),
            sa.ForeignKey("ppe_personal_cards.id"),
            nullable=False,
        ),
        sa.Column("ppe_catalog_id", sa.String(36), sa.ForeignKey("ppe_catalog.id"), nullable=False),
        sa.Column("last_issue_id", sa.String(36), sa.ForeignKey("ppe_issues.id"), nullable=True),
        sa.Column("current_quantity", sa.Numeric(10, 2), nullable=False, server_default="0"),
        sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_index(
        "ix_persons_filter",
        "persons",
        ["tenant_id", "company_id", "site_id", "position_id", "employment_status"],
    )
    op.create_index("ix_workplaces_filter", "workplaces", ["tenant_id", "site_id", "department_id"])
    op.create_index(
        "ix_risk_maps_filter",
        "risk_maps",
        ["tenant_id", "entity_type", "entity_id", "status", "updated_at"],
    )
    op.create_index("ix_risk_map_items_level", "risk_map_items", ["risk_map_id", "risk_level"])
    op.create_index(
        "ix_ppe_norm_items_filter",
        "ppe_norm_items",
        ["ppe_norm_id", "applies_to_type", "applies_to_id"],
    )
    op.create_index(
        "ix_ppe_issues_filter",
        "ppe_issues",
        ["tenant_id", "person_id", "ppe_catalog_id", "issued_at"],
    )
    op.create_index(
        "ix_ppe_personal_card_items_filter",
        "ppe_personal_card_items",
        ["personal_card_id", "ppe_catalog_id"],
    )


def downgrade() -> None:
    for idx, table in [
        ("ix_ppe_personal_card_items_filter", "ppe_personal_card_items"),
        ("ix_ppe_issues_filter", "ppe_issues"),
        ("ix_ppe_norm_items_filter", "ppe_norm_items"),
        ("ix_risk_map_items_level", "risk_map_items"),
        ("ix_risk_maps_filter", "risk_maps"),
        ("ix_workplaces_filter", "workplaces"),
        ("ix_persons_filter", "persons"),
    ]:
        op.drop_index(idx, table_name=table)

    for table in [
        "ppe_personal_card_items",
        "ppe_personal_cards",
        "ppe_issues",
        "ppe_norm_items",
        "ppe_norms",
        "ppe_catalog",
        "risk_map_item_measures",
        "risk_map_items",
        "risk_maps",
        "hazard_bindings",
        "hazard_measures",
        "risk_measures",
        "hazards",
        "risk_methodologies",
        "persons",
        "workplaces",
        "positions",
        "departments",
        "sites",
        "companies",
    ]:
        op.drop_table(table)
