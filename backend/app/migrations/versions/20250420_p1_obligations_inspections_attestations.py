"""Expand obligations with inspections, attestations, and prescriptions."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20250420_p1_obligations_inspections_attestations"
down_revision = "20250410_p1_entities_tasks_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspection_type = sa.Enum("internal", "external", name="inspectiontype")
    attestation_status = sa.Enum("active", "expired", "revoked", name="attestationstatus")
    prescription_status = sa.Enum(
        "open", "in_progress", "completed", "cancelled", name="prescriptionstatus"
    )
    if bind.dialect.name == "postgresql":
        inspection_type.create(bind, checkfirst=True)
        attestation_status.create(bind, checkfirst=True)
        prescription_status.create(bind, checkfirst=True)

    op.add_column(
        "regulatory_inspection",
        sa.Column(
            "inspection_type",
            inspection_type,
            nullable=False,
            server_default="internal",
        ),
    )
    op.add_column(
        "regulatory_inspection",
        sa.Column("responsible_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "regulatory_inspection",
        sa.Column("recurrence_rule", sa.String(length=128), nullable=True),
    )
    op.create_foreign_key(
        "fk_regulatory_inspection_responsible",
        "regulatory_inspection",
        "user",
        ["responsible_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_regulatory_inspection_responsible",
        "regulatory_inspection",
        ["tenant_id", "responsible_id"],
        unique=False,
    )
    op.create_index(
        "ix_regulatory_inspection_type",
        "regulatory_inspection",
        ["tenant_id", "inspection_type"],
        unique=False,
    )

    op.create_table(
        "attestation",
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("issued_at", sa.Date(), nullable=True),
        sa.Column("expires_at", sa.Date(), nullable=True),
        sa.Column("status", attestation_status, nullable=False),
        sa.Column("responsible_id", sa.String(length=36), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["position_id"], ["position.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["responsible_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attestation_person", "attestation", ["tenant_id", "person_id"], unique=False)
    op.create_index("ix_attestation_status", "attestation", ["tenant_id", "status"], unique=False)
    op.create_index("ix_attestation_expires", "attestation", ["tenant_id", "expires_at"], unique=False)

    op.create_table(
        "inspection_prescription",
        sa.Column("inspection_id", sa.String(length=36), nullable=False),
        sa.Column("incident_id", sa.String(length=36), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("due_at", sa.Date(), nullable=True),
        sa.Column("status", prescription_status, nullable=False),
        sa.Column("assignee_id", sa.String(length=36), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["inspection_id"], ["regulatory_inspection.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["incident_id"], ["incident.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["assignee_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_prescription_inspection",
        "inspection_prescription",
        ["tenant_id", "inspection_id"],
        unique=False,
    )
    op.create_index(
        "ix_prescription_status",
        "inspection_prescription",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_prescription_due",
        "inspection_prescription",
        ["tenant_id", "due_at"],
        unique=False,
    )
    op.create_index(
        "ix_prescription_assignee",
        "inspection_prescription",
        ["tenant_id", "assignee_id"],
        unique=False,
    )

    op.alter_column("regulatory_inspection", "inspection_type", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspection_type = sa.Enum("internal", "external", name="inspectiontype")
    attestation_status = sa.Enum("active", "expired", "revoked", name="attestationstatus")
    prescription_status = sa.Enum(
        "open", "in_progress", "completed", "cancelled", name="prescriptionstatus"
    )

    op.drop_index("ix_prescription_assignee", table_name="inspection_prescription")
    op.drop_index("ix_prescription_due", table_name="inspection_prescription")
    op.drop_index("ix_prescription_status", table_name="inspection_prescription")
    op.drop_index("ix_prescription_inspection", table_name="inspection_prescription")
    op.drop_table("inspection_prescription")

    op.drop_index("ix_attestation_expires", table_name="attestation")
    op.drop_index("ix_attestation_status", table_name="attestation")
    op.drop_index("ix_attestation_person", table_name="attestation")
    op.drop_table("attestation")

    op.drop_index("ix_regulatory_inspection_type", table_name="regulatory_inspection")
    op.drop_index("ix_regulatory_inspection_responsible", table_name="regulatory_inspection")
    op.drop_constraint(
        "fk_regulatory_inspection_responsible", "regulatory_inspection", type_="foreignkey"
    )
    op.drop_column("regulatory_inspection", "recurrence_rule")
    op.drop_column("regulatory_inspection", "responsible_id")
    op.drop_column("regulatory_inspection", "inspection_type")

    if bind.dialect.name == "postgresql":
        prescription_status.drop(bind, checkfirst=True)
        attestation_status.drop(bind, checkfirst=True)
        inspection_type.drop(bind, checkfirst=True)
