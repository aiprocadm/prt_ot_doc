"""Expand company requisites and employee safety metadata

Revision ID: 4a45e0c64b41
Revises: 6b6dee7c951f
Create Date: 2024-02-29 00:00:00.000000

"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "4a45e0c64b41"
down_revision: str = "6b6dee7c951f"
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
        batch.add_column(sa.Column("kpp", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("ogrn", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("actual_address", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("director", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("bank_name", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("bank_bik", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("bank_account", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column(
                "phone_numbers",
                json_type,
                nullable=False,
                server_default=json_default,
            )
        )
        batch.add_column(sa.Column("email", sa.String(length=320), nullable=True))
        batch.add_column(sa.Column("logo_file_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("stamp_file_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column(
                "work_types",
                json_type,
                nullable=False,
                server_default=json_default,
            )
        )
        batch.add_column(
            sa.Column(
                "hazardous_factors",
                json_type,
                nullable=False,
                server_default=json_default,
            )
        )
        batch.alter_column("phone_numbers", server_default=None)
        batch.alter_column("work_types", server_default=None)
        batch.alter_column("hazardous_factors", server_default=None)

    op.create_foreign_key(
        "fk_company_logo_file",
        "company",
        "file",
        ["logo_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_company_stamp_file",
        "company",
        "file",
        ["stamp_file_id"],
        ["id"],
        ondelete="SET NULL",
    )

    with op.batch_alter_table("person", schema=None) as batch:
        batch.add_column(sa.Column("personnel_number", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("hired_at", sa.Date(), nullable=True))
        batch.add_column(
            sa.Column(
                "qualifications",
                json_type,
                nullable=False,
                server_default=json_default,
            )
        )
        batch.add_column(sa.Column("snils", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("passport", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column(
                "current_ppe",
                json_type,
                nullable=False,
                server_default=json_default,
            )
        )
        batch.create_unique_constraint(
            "uq_person_tenant_tab_number", ["tenant_id", "personnel_number"]
        )
        batch.alter_column("qualifications", server_default=None)
        batch.alter_column("current_ppe", server_default=None)

    op.create_index(
        "ix_person_personnel_number",
        "person",
        ["personnel_number"],
        unique=False,
    )

    with op.batch_alter_table("ppe_norm", schema=None) as batch:
        batch.add_column(sa.Column("hazard_id", sa.String(length=36), nullable=True))
        batch.create_unique_constraint(
            "uq_ppe_norm_position_hazard_item",
            ["tenant_id", "position_id", "hazard_id", "item_name"],
        )

    # backfill hazard references for existing PPE norms
    result = bind.execute(sa.text("SELECT DISTINCT tenant_id FROM ppe_norm WHERE hazard_id IS NULL"))
    tenants = [row[0] for row in result]
    now = datetime.now(timezone.utc)
    for tenant_id in tenants:
        hazard_id = str(uuid4())
        bind.execute(
            sa.text(
                """
                INSERT INTO risk_hazards (
                    id, created_at, updated_at, version, tenant_id, code, title, module
                ) VALUES (:id, :created_at, :updated_at, :version, :tenant_id, :code, :title, :module)
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "id": hazard_id,
                "created_at": now,
                "updated_at": now,
                "version": 1,
                "tenant_id": tenant_id,
                "code": "legacy_ppe_norm",
                "title": "Legacy PPE requirement",
                "module": "ot",
            },
        )
        bind.execute(
            sa.text(
                "UPDATE ppe_norm SET hazard_id = :hazard_id WHERE tenant_id = :tenant_id AND hazard_id IS NULL"
            ),
            {"hazard_id": hazard_id, "tenant_id": tenant_id},
        )

    with op.batch_alter_table("ppe_norm", schema=None) as batch:
        batch.alter_column("hazard_id", existing_type=sa.String(length=36), nullable=False)

    op.create_foreign_key(
        "fk_ppe_norm_hazard",
        "ppe_norm",
        "risk_hazards",
        ["hazard_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_ppe_norm_hazard_id", "ppe_norm", ["hazard_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_ppe_norm_hazard_id", table_name="ppe_norm")
    op.drop_constraint("fk_ppe_norm_hazard", "ppe_norm", type_="foreignkey")
    with op.batch_alter_table("ppe_norm", schema=None) as batch:
        batch.drop_constraint("uq_ppe_norm_position_hazard_item", type_="unique")
        batch.drop_column("hazard_id")

    # remove placeholder hazards that were introduced during upgrade
    bind.execute(
        sa.text("DELETE FROM risk_hazards WHERE code = :code"),
        {"code": "legacy_ppe_norm"},
    )

    op.drop_index("ix_person_personnel_number", table_name="person")
    with op.batch_alter_table("person", schema=None) as batch:
        batch.drop_constraint("uq_person_tenant_tab_number", type_="unique")
        batch.drop_column("current_ppe")
        batch.drop_column("passport")
        batch.drop_column("snils")
        batch.drop_column("qualifications")
        batch.drop_column("hired_at")
        batch.drop_column("personnel_number")

    op.drop_constraint("fk_company_stamp_file", "company", type_="foreignkey")
    op.drop_constraint("fk_company_logo_file", "company", type_="foreignkey")
    with op.batch_alter_table("company", schema=None) as batch:
        batch.drop_column("hazardous_factors")
        batch.drop_column("work_types")
        batch.drop_column("stamp_file_id")
        batch.drop_column("logo_file_id")
        batch.drop_column("email")
        batch.drop_column("phone_numbers")
        batch.drop_column("bank_account")
        batch.drop_column("bank_bik")
        batch.drop_column("bank_name")
        batch.drop_column("director")
        batch.drop_column("actual_address")
        batch.drop_column("ogrn")
        batch.drop_column("kpp")

