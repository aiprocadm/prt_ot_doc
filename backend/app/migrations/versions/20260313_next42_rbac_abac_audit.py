"""next42 rbac-abac policies and immutable audit fields

Revision ID: 20260313_next42_rbac_abac_audit
Revises: 20260312_next41_files_bus
Create Date: 2026-03-13
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260313_next42_rbac_abac_audit"
down_revision = "20260312_next41"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("authz_roles") as batch:
        batch.add_column(sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint("uq_authz_roles_tenant_code", ["tenant_id", "code"])

    with op.batch_alter_table("authz_permissions") as batch:
        batch.add_column(sa.Column("description", sa.String(length=512), nullable=True))

    with op.batch_alter_table("authz_role_permissions") as batch:
        batch.add_column(sa.Column("permission_code", sa.String(length=255), nullable=True))

    op.execute(
        """
        UPDATE authz_role_permissions arp
        SET permission_code = ap.code
        FROM authz_permissions ap
        WHERE arp.permission_id = ap.id AND arp.permission_code IS NULL
        """
    )

    with op.batch_alter_table("authz_role_permissions") as batch:
        batch.alter_column("permission_code", existing_type=sa.String(length=255), nullable=False)
        batch.create_unique_constraint(
            "uq_authz_role_permissions_tenant_role_code",
            ["tenant_id", "role_id", "permission_code"],
        )

    with op.batch_alter_table("authz_user_roles") as batch:
        batch.add_column(sa.Column("scope_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.create_unique_constraint("uq_authz_user_roles_tenant_user_role", ["tenant_id", "user_id", "role_id"])

    op.create_table(
        "authz_policies",
        sa.Column("resource", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("effect", sa.String(length=8), nullable=False),
        sa.Column("conditions_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_authz_policy_lookup",
        "authz_policies",
        ["tenant_id", "resource", "action", "enabled", "priority"],
        unique=False,
    )

    with op.batch_alter_table("auditlog") as batch:
        batch.add_column(sa.Column("before_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("after_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("actor_role_codes", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))


def downgrade() -> None:
    with op.batch_alter_table("auditlog") as batch:
        batch.drop_column("actor_role_codes")
        batch.drop_column("after_json")
        batch.drop_column("before_json")

    op.drop_index("ix_authz_policy_lookup", table_name="authz_policies")
    op.drop_table("authz_policies")

    with op.batch_alter_table("authz_user_roles") as batch:
        batch.drop_constraint("uq_authz_user_roles_tenant_user_role", type_="unique")
        batch.drop_column("scope_json")

    with op.batch_alter_table("authz_role_permissions") as batch:
        batch.drop_constraint("uq_authz_role_permissions_tenant_role_code", type_="unique")
        batch.drop_column("permission_code")

    with op.batch_alter_table("authz_permissions") as batch:
        batch.drop_column("description")

    with op.batch_alter_table("authz_roles") as batch:
        batch.drop_constraint("uq_authz_roles_tenant_code", type_="unique")
        batch.drop_column("deleted_at")
        batch.drop_column("is_system")
