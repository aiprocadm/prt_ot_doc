"""Expand OT domain with workplaces and hazard links

Revision ID: 20250218_ot_hazards_workplaces
Revises: 4a45e0c64b41
Create Date: 2025-02-18 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20250218_ot_hazards_workplaces"
down_revision: str = "4a45e0c64b41"
branch_labels = None
depends_on = None


def _json_type(bind) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _json_default(bind) -> sa.sql.elements.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text("'[]'::jsonb")
    return sa.text("'[]'")


def upgrade() -> None:
    bind = op.get_bind()
    json_type = _json_type(bind)
    json_default = _json_default(bind)

    with op.batch_alter_table("company", schema=None) as batch:
        batch.add_column(sa.Column("activity_type", sa.String(length=128), nullable=True))
        batch.add_column(
            sa.Column("okved_codes", json_type, nullable=False, server_default=json_default)
        )
        batch.add_column(sa.Column("contact_person", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("contact_phone", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("contact_email", sa.String(length=320), nullable=True))
        batch.add_column(
            sa.Column(
                "is_hazardous_production_facility",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch.add_column(
            sa.Column(
                "has_dangerous_objects",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch.alter_column("okved_codes", server_default=None)
        batch.alter_column("is_hazardous_production_facility", server_default=None)
        batch.alter_column("has_dangerous_objects", server_default=None)

    with op.batch_alter_table("position", schema=None) as batch:
        batch.add_column(sa.Column("safety_category", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("working_conditions_class", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column("hazardous_factors", json_type, nullable=False, server_default=json_default)
        )
        batch.alter_column("hazardous_factors", server_default=None)

    with op.batch_alter_table("person", schema=None) as batch:
        batch.add_column(sa.Column("workplace_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("working_conditions_class", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column("hazardous_factors", json_type, nullable=False, server_default=json_default)
        )
        batch.alter_column("hazardous_factors", server_default=None)

    with op.batch_alter_table("site", schema=None) as batch:
        batch.add_column(sa.Column("site_type", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("contact_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("contact_phone", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("contact_email", sa.String(length=320), nullable=True))
        batch.add_column(
            sa.Column(
                "is_hazardous_production_facility",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            )
        )
        batch.add_column(sa.Column("opo_register_number", sa.String(length=64), nullable=True))
        batch.alter_column("is_hazardous_production_facility", server_default=None)

    op.create_table(
        "workplace",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("working_conditions_class", sa.String(length=32), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["company_id"], ["company.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "company_id", "name", name="uq_workplace_company_name"),
    )
    op.create_index("ix_workplace_company", "workplace", ["company_id"], unique=False)
    op.create_index("ix_workplace_site", "workplace", ["site_id"], unique=False)
    op.create_index("ix_workplace_tenant", "workplace", ["tenant_id"], unique=False)

    op.create_table(
        "workplace_hazard",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("workplace_id", sa.String(length=36), nullable=False),
        sa.Column("hazard_id", sa.String(length=36), nullable=False),
        sa.Column("document_file_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["document_file_id"], ["file.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hazard_id"], ["risk_hazards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workplace_id"], ["workplace.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "workplace_id", "hazard_id", name="uq_workplace_hazard_link"
        ),
    )
    op.create_index(
        "ix_workplace_hazard_workplace_id", "workplace_hazard", ["workplace_id"], unique=False
    )
    op.create_index(
        "ix_workplace_hazard_hazard_id", "workplace_hazard", ["hazard_id"], unique=False
    )

    op.create_table(
        "position_hazard",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("position_id", sa.String(length=36), nullable=False),
        sa.Column("hazard_id", sa.String(length=36), nullable=False),
        sa.Column("document_file_id", sa.String(length=36), nullable=True),
        sa.ForeignKeyConstraint(["document_file_id"], ["file.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["hazard_id"], ["risk_hazards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["position_id"], ["position.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "position_id", "hazard_id", name="uq_position_hazard_link"
        ),
    )
    op.create_index(
        "ix_position_hazard_position_id", "position_hazard", ["position_id"], unique=False
    )
    op.create_index("ix_position_hazard_hazard_id", "position_hazard", ["hazard_id"], unique=False)

    with op.batch_alter_table("risk_hazards", schema=None) as batch:
        batch.add_column(sa.Column("document_file_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_risk_hazard_document_file",
        "risk_hazards",
        "file",
        ["document_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_person_workplace",
        "person",
        "workplace",
        ["workplace_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_person_workplace", "person", type_="foreignkey")
    with op.batch_alter_table("risk_hazards", schema=None) as batch:
        batch.drop_constraint("fk_risk_hazard_document_file", type_="foreignkey")
        batch.drop_column("document_file_id")

    op.drop_index("ix_position_hazard_hazard_id", table_name="position_hazard")
    op.drop_index("ix_position_hazard_position_id", table_name="position_hazard")
    op.drop_table("position_hazard")

    op.drop_index("ix_workplace_hazard_hazard_id", table_name="workplace_hazard")
    op.drop_index("ix_workplace_hazard_workplace_id", table_name="workplace_hazard")
    op.drop_table("workplace_hazard")

    op.drop_index("ix_workplace_tenant", table_name="workplace")
    op.drop_index("ix_workplace_site", table_name="workplace")
    op.drop_index("ix_workplace_company", table_name="workplace")
    op.drop_table("workplace")

    with op.batch_alter_table("site", schema=None) as batch:
        batch.drop_column("opo_register_number")
        batch.drop_column("is_hazardous_production_facility")
        batch.drop_column("contact_email")
        batch.drop_column("contact_phone")
        batch.drop_column("contact_name")
        batch.drop_column("site_type")

    with op.batch_alter_table("person", schema=None) as batch:
        batch.drop_column("hazardous_factors")
        batch.drop_column("working_conditions_class")
        batch.drop_column("workplace_id")

    with op.batch_alter_table("position", schema=None) as batch:
        batch.drop_column("hazardous_factors")
        batch.drop_column("working_conditions_class")
        batch.drop_column("safety_category")

    with op.batch_alter_table("company", schema=None) as batch:
        batch.drop_column("has_dangerous_objects")
        batch.drop_column("is_hazardous_production_facility")
        batch.drop_column("contact_email")
        batch.drop_column("contact_phone")
        batch.drop_column("contact_person")
        batch.drop_column("okved_codes")
        batch.drop_column("activity_type")
