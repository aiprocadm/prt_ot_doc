"""con01: contractors domain core + documents registry (TZ B.14 Срез-2).

Additive. Creates the contractors-domain core tables that exist only in the ORM
(``app.modules.contractors.models``) and were never migrated on PG:
``contractor_registry``, ``contractor_employees``, ``contractor_incidents`` — plus
the original ``contractor_documents`` table this migration shipped. The first three
are the natural parents of the FKs ``contractor_documents`` declares, so creating
them here (before the child) is the correct owner-migration fix for the missing-table
chain (CI: ``UndefinedTableError: relation "contractor_registry" does not exist``).

``contractor_employees`` / ``contractor_incidents`` carry native PG enum columns. The
ORM declares them as plain ``Enum(EnumClass, name=...)`` (NO ``values_callable``), so
SQLAlchemy persists member NAMES (UPPER) and creates the PG type with UPPER labels —
mirrored here (iter-43 convention). Enum types are created before their owning tables
and dropped on downgrade after them (orphan-type lesson, PR #639).

VARCHAR doc_type/status on ``contractor_documents`` (no enum types) — unchanged.

Retry-safe under AUTOCOMMIT (env.py): table creates are guarded by a metadata check
and enum creates use ``checkfirst=True`` so a mid-migration failure can be re-run.
Round-trip-safe: downgrade drops children before parents, indexes before tables, and
enum types last; no orphan enum types.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260609_con01_contractor_documents"
down_revision = "20260607_med01_medical_domain"
branch_labels = None
depends_on = None


# ComplianceStatus member NAMES (UPPER) — SA default storage form for
# Enum(EnumClass) without values_callable. Mirrors
# app.modules.contractors.models.ComplianceStatus.
_COMPLIANCE_VALUES = ("VALID", "PENDING", "EXPIRED", "BLOCKED")
# IncidentSeverity member NAMES (UPPER) — same convention.
_SEVERITY_VALUES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")

_ACCESS_STATUS = postgresql.ENUM(*_COMPLIANCE_VALUES, name="contractor_access_status", create_type=False)
_TRAINING_STATUS = postgresql.ENUM(*_COMPLIANCE_VALUES, name="contractor_training_status", create_type=False)
_MEDICAL_STATUS = postgresql.ENUM(*_COMPLIANCE_VALUES, name="contractor_medical_status", create_type=False)
_INCIDENT_SEVERITY = postgresql.ENUM(*_SEVERITY_VALUES, name="contractor_incident_severity", create_type=False)


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    return sa.inspect(bind).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()

    # --- enum types (created before the tables that use them) ----------------
    for enum_type in (_ACCESS_STATUS, _TRAINING_STATUS, _MEDICAL_STATUS, _INCIDENT_SEVERITY):
        enum_type.create(bind, checkfirst=True)

    # --- contractor_registry (parent of all contractor_* FKs) ----------------
    if not _has_table("contractor_registry"):
        op.create_table(
            "contractor_registry",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("company_id", sa.String(length=36), nullable=True, index=True),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("legal_name", sa.String(length=255), nullable=True),
            sa.Column("inn", sa.String(length=32), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
            sa.Column("contact_person", sa.String(length=255), nullable=True),
            sa.Column("contact_phone", sa.String(length=64), nullable=True),
        )
        op.create_index("ix_contractor_registry_tenant_status", "contractor_registry", ["tenant_id", "status"])
        op.create_index("ix_contractor_registry_tenant_company", "contractor_registry", ["tenant_id", "company_id"])

    # --- contractor_employees -------------------------------------------------
    if not _has_table("contractor_employees"):
        op.create_table(
            "contractor_employees",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "contractor_id", sa.String(length=36),
                sa.ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column("full_name", sa.String(length=255), nullable=False),
            sa.Column("position", sa.String(length=255), nullable=True),
            sa.Column("personnel_number", sa.String(length=64), nullable=True),
            sa.Column("access_status", _ACCESS_STATUS, nullable=False, server_default="PENDING"),
            sa.Column("training_status", _TRAINING_STATUS, nullable=False, server_default="PENDING"),
            sa.Column("medical_status", _MEDICAL_STATUS, nullable=False, server_default="PENDING"),
            sa.Column("last_training_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_medical_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_contractor_employees_contractor_id", "contractor_employees", ["contractor_id"])
        op.create_index("ix_contractor_employees_tenant_contractor", "contractor_employees", ["tenant_id", "contractor_id"])
        op.create_index("ix_contractor_employees_tenant_training", "contractor_employees", ["tenant_id", "training_status"])
        op.create_index("ix_contractor_employees_tenant_medical", "contractor_employees", ["tenant_id", "medical_status"])

    # --- contractor_incidents -------------------------------------------------
    if not _has_table("contractor_incidents"):
        op.create_table(
            "contractor_incidents",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "contractor_id", sa.String(length=36),
                sa.ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "employee_id", sa.String(length=36),
                sa.ForeignKey("contractor_employees.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("incident_type", sa.String(length=64), nullable=False),
            sa.Column("severity", _INCIDENT_SEVERITY, nullable=False, server_default="MEDIUM"),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="open"),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
        )
        op.create_index("ix_contractor_incidents_contractor_id", "contractor_incidents", ["contractor_id"])
        op.create_index("ix_contractor_incidents_employee_id", "contractor_incidents", ["employee_id"])
        op.create_index("ix_contractor_incidents_tenant_contractor", "contractor_incidents", ["tenant_id", "contractor_id"])
        op.create_index("ix_contractor_incidents_tenant_status", "contractor_incidents", ["tenant_id", "status"])

    # --- contractor_documents (original con01 payload) ------------------------
    if not _has_table("contractor_documents"):
        op.create_table(
            "contractor_documents",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("tenant_id", sa.String(length=36), nullable=False, index=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "contractor_id", sa.String(length=36),
                sa.ForeignKey("contractor_registry.id", ondelete="CASCADE"), nullable=False,
            ),
            sa.Column(
                "employee_id", sa.String(length=36),
                sa.ForeignKey("contractor_employees.id", ondelete="SET NULL"), nullable=True,
            ),
            sa.Column("doc_type", sa.String(length=64), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=False),
            sa.Column("number", sa.String(length=128), nullable=True),
            sa.Column("issuing_org", sa.String(length=255), nullable=True),
            sa.Column("issued_at", sa.Date(), nullable=True),
            sa.Column("valid_until", sa.Date(), nullable=True),
            sa.Column("file_id", sa.String(length=36), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        )
        op.create_index("ix_contractor_documents_tenant_contractor", "contractor_documents", ["tenant_id", "contractor_id"])
        op.create_index("ix_contractor_documents_tenant_employee", "contractor_documents", ["tenant_id", "employee_id"])
        op.create_index("ix_contractor_documents_tenant_valid", "contractor_documents", ["tenant_id", "valid_until"])
        op.create_index("ix_contractor_documents_tenant_type", "contractor_documents", ["tenant_id", "doc_type"])


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_contractor_documents_tenant_type", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_valid", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_employee", table_name="contractor_documents")
    op.drop_index("ix_contractor_documents_tenant_contractor", table_name="contractor_documents")
    op.drop_table("contractor_documents")

    op.drop_index("ix_contractor_incidents_tenant_status", table_name="contractor_incidents")
    op.drop_index("ix_contractor_incidents_tenant_contractor", table_name="contractor_incidents")
    op.drop_index("ix_contractor_incidents_employee_id", table_name="contractor_incidents")
    op.drop_index("ix_contractor_incidents_contractor_id", table_name="contractor_incidents")
    op.drop_table("contractor_incidents")

    op.drop_index("ix_contractor_employees_tenant_medical", table_name="contractor_employees")
    op.drop_index("ix_contractor_employees_tenant_training", table_name="contractor_employees")
    op.drop_index("ix_contractor_employees_tenant_contractor", table_name="contractor_employees")
    op.drop_index("ix_contractor_employees_contractor_id", table_name="contractor_employees")
    op.drop_table("contractor_employees")

    op.drop_index("ix_contractor_registry_tenant_company", table_name="contractor_registry")
    op.drop_index("ix_contractor_registry_tenant_status", table_name="contractor_registry")
    op.drop_table("contractor_registry")

    if bind.dialect.name == "postgresql":
        for type_name in (
            "contractor_incident_severity",
            "contractor_medical_status",
            "contractor_training_status",
            "contractor_access_status",
        ):
            op.execute(f"DROP TYPE IF EXISTS {type_name}")
