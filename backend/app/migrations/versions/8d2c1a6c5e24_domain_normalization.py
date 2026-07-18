"""domain normalization"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8d2c1a6c5e24"
down_revision: str = "4a45e0c64b41"
branch_labels = None
depends_on = None


def _json_type(bind) -> sa.types.TypeEngine:
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _json_object_default(bind) -> sa.sql.elements.TextClause:
    if bind.dialect.name == "postgresql":
        return sa.text("'{}'::jsonb")
    return sa.text("'{}'")


def _resolve_npa_binding_table(bind) -> str | None:
    inspector = sa.inspect(bind)
    if inspector.has_table("npa_binding"):
        return "npa_binding"
    if inspector.has_table("npabinding"):
        return "npabinding"
    return None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = _json_type(bind)
    json_default = _json_object_default(bind)
    npa_binding_table = _resolve_npa_binding_table(bind)

    employment_status = postgresql.ENUM(
        "active",
        "on_leave",
        "suspended",
        "terminated",
        name="employmentstatus",
        create_type=False,
    )
    document_pack_module = postgresql.ENUM(
        "ot",
        "fire_safety",
        "health",
        "custom",
        name="documentpackmodule",
        create_type=False,
    )
    document_pack_scenario = postgresql.ENUM(
        "document_batch",
        "report",
        "workflow",
        name="documentpackscenario",
        create_type=False,
    )
    document_version_status = postgresql.ENUM(
        "draft",
        "locked",
        "published",
        "archived",
        name="documentversionstatus",
        create_type=False,
    )
    npa_binding_target = postgresql.ENUM(
        "template_version",
        "document",
        "pack",
        name="npabindingtarget",
        create_type=False,
    )

    employment_status.create(bind, checkfirst=True)
    document_pack_module.create(bind, checkfirst=True)
    document_pack_scenario.create(bind, checkfirst=True)
    document_version_status.create(bind, checkfirst=True)
    npa_binding_target.create(bind, checkfirst=True)

    with op.batch_alter_table("site", schema=None) as batch:
        batch.add_column(sa.Column("geo_json", json_type, nullable=True))
        batch.add_column(sa.Column("hazard_class", sa.String(length=32), nullable=True))

    with op.batch_alter_table("person", schema=None) as batch:
        batch.add_column(sa.Column("phone", sa.String(length=32), nullable=True))
        batch.add_column(
            sa.Column(
                "employment_status",
                employment_status,
                nullable=False,
                server_default="active",
            )
        )
        batch.alter_column("employment_status", server_default=None)

    with op.batch_alter_table("document", schema=None) as batch:
        batch.add_column(sa.Column("site_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("template_version_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("file_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("signed_file_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("content_sha256", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("job_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_document_site",
        "document",
        "site",
        ["site_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_document_template_version",
        "document",
        "templateversion",
        ["template_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_document_file",
        "document",
        "file",
        ["file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_document_signed_file",
        "document",
        "file",
        ["signed_file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_document_job",
        "document",
        "documentgenerationjob",
        ["job_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_template_version",
        "document",
        ["tenant_id", "template_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_site",
        "document",
        ["tenant_id", "site_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_job",
        "document",
        ["tenant_id", "job_id"],
        unique=False,
    )

    with op.batch_alter_table("documentversion", schema=None) as batch:
        batch.add_column(sa.Column("file_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("template_version_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column(
                "version_number",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch.add_column(
            sa.Column(
                "status",
                document_version_status,
                nullable=False,
                server_default="draft",
            )
        )
        batch.alter_column("version_number", server_default=None)
        batch.alter_column("status", server_default=None)
    op.create_foreign_key(
        "fk_document_version_file",
        "documentversion",
        "file",
        ["file_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_document_version_template",
        "documentversion",
        "templateversion",
        ["template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_version_template_version",
        "documentversion",
        ["tenant_id", "template_version_id"],
        unique=False,
    )

    with op.batch_alter_table("document_pack", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "module",
                document_pack_module,
                nullable=False,
                server_default="ot",
            )
        )
        batch.add_column(
            sa.Column(
                "scenario_type",
                document_pack_scenario,
                nullable=False,
                server_default="document_batch",
            )
        )
        batch.alter_column("module", server_default=None)
        batch.alter_column("scenario_type", server_default=None)

    with op.batch_alter_table("document_pack_item", schema=None) as batch:
        batch.add_column(sa.Column("template_version_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(
        "fk_pack_item_template_version",
        "document_pack_item",
        "templateversion",
        ["template_version_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_pack_item_template_version_id",
        "document_pack_item",
        ["template_version_id"],
        unique=False,
    )

    with op.batch_alter_table("documentgenerationjob", schema=None) as batch:
        batch.add_column(sa.Column("pack_id", sa.String(length=36), nullable=True))
        batch.add_column(
            sa.Column(
                "payload",
                json_type,
                nullable=False,
                server_default=json_default,
            )
        )
        batch.add_column(
            sa.Column(
                "queued_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))
        batch.alter_column("payload", server_default=None)
    op.create_foreign_key(
        "fk_document_job_pack",
        "documentgenerationjob",
        "document_pack",
        ["pack_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_document_job_pack_id",
        "documentgenerationjob",
        ["tenant_id", "pack_id"],
        unique=False,
    )

    if npa_binding_table:
        with op.batch_alter_table(npa_binding_table, schema=None) as batch:
            batch.add_column(sa.Column("entity_type", npa_binding_target, nullable=True))
            batch.add_column(sa.Column("entity_id", sa.String(length=36), nullable=True))
            batch.add_column(
                sa.Column(
                    "context",
                    json_type,
                    nullable=False,
                    server_default=json_default,
                )
            )
            batch.alter_column("context", server_default=None)
            batch.alter_column(
                "template_version_id", existing_type=sa.String(length=36), nullable=True
            )
        op.execute(
            sa.text(
                f"UPDATE {npa_binding_table} SET entity_type = 'template_version', entity_id = template_version_id "
                "WHERE entity_type IS NULL"
            )
        )
        with op.batch_alter_table(npa_binding_table, schema=None) as batch:
            batch.alter_column("entity_type", nullable=False)
            batch.alter_column("entity_id", nullable=False)

    with op.batch_alter_table("file", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "bucket",
                sa.String(length=255),
                nullable=False,
                server_default="default",
            )
        )
        batch.alter_column("bucket", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    npa_binding_table = _resolve_npa_binding_table(bind)

    op.drop_index("ix_document_pack_item_template_version_id", table_name="document_pack_item")
    op.drop_constraint("fk_pack_item_template_version", "document_pack_item", type_="foreignkey")
    with op.batch_alter_table("document_pack_item", schema=None) as batch:
        batch.drop_column("template_version_id")

    op.drop_index("ix_document_job_pack_id", table_name="documentgenerationjob")
    op.drop_constraint("fk_document_job_pack", "documentgenerationjob", type_="foreignkey")
    with op.batch_alter_table("documentgenerationjob", schema=None) as batch:
        batch.drop_column("finished_at")
        batch.drop_column("started_at")
        batch.drop_column("queued_at")
        batch.drop_column("payload")
        batch.drop_column("pack_id")

    op.drop_index("ix_document_version_template_version", table_name="documentversion")
    op.drop_constraint("fk_document_version_template", "documentversion", type_="foreignkey")
    op.drop_constraint("fk_document_version_file", "documentversion", type_="foreignkey")
    with op.batch_alter_table("documentversion", schema=None) as batch:
        batch.drop_column("status")
        batch.drop_column("version_number")
        batch.drop_column("template_version_id")
        batch.drop_column("file_id")

    op.drop_index("ix_document_job", table_name="document")
    op.drop_index("ix_document_site", table_name="document")
    op.drop_index("ix_document_template_version", table_name="document")
    op.drop_constraint("fk_document_job", "document", type_="foreignkey")
    op.drop_constraint("fk_document_signed_file", "document", type_="foreignkey")
    op.drop_constraint("fk_document_file", "document", type_="foreignkey")
    op.drop_constraint("fk_document_template_version", "document", type_="foreignkey")
    op.drop_constraint("fk_document_site", "document", type_="foreignkey")
    with op.batch_alter_table("document", schema=None) as batch:
        batch.drop_column("job_id")
        batch.drop_column("content_sha256")
        batch.drop_column("signed_file_id")
        batch.drop_column("file_id")
        batch.drop_column("template_version_id")
        batch.drop_column("site_id")

    with op.batch_alter_table("document_pack", schema=None) as batch:
        batch.drop_column("scenario_type")
        batch.drop_column("module")

    if npa_binding_table:
        op.execute(
            sa.text(f"DELETE FROM {npa_binding_table} WHERE entity_type <> 'template_version'")
        )
        op.execute(
            sa.text(
                f"UPDATE {npa_binding_table} SET template_version_id = entity_id "
                "WHERE entity_type = 'template_version' AND template_version_id IS NULL"
            )
        )

        with op.batch_alter_table(npa_binding_table, schema=None) as batch:
            batch.drop_column("context")
            batch.drop_column("entity_id")
            batch.drop_column("entity_type")
            batch.alter_column(
                "template_version_id", existing_type=sa.String(length=36), nullable=False
            )

    with op.batch_alter_table("file", schema=None) as batch:
        batch.drop_column("bucket")

    with op.batch_alter_table("site", schema=None) as batch:
        batch.drop_column("hazard_class")
        batch.drop_column("geo_json")

    with op.batch_alter_table("person", schema=None) as batch:
        batch.drop_column("employment_status")
        batch.drop_column("phone")

    sa.Enum(name="npabindingtarget").drop(bind, checkfirst=True)
    sa.Enum(name="documentversionstatus").drop(bind, checkfirst=True)
    sa.Enum(name="documentpackscenario").drop(bind, checkfirst=True)
    sa.Enum(name="documentpackmodule").drop(bind, checkfirst=True)
    sa.Enum(name="employmentstatus").drop(bind, checkfirst=True)
