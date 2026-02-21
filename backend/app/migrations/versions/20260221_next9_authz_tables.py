"""Add RBAC/ABAC authorization catalog tables.

Revision ID: 20260221_next9_authz_tables
Revises: 20260221_next7_user_attributes
Create Date: 2026-02-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260221_next9_authz_tables"
down_revision = "20260221_next7_user_attributes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "authz_roles",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )

    op.create_table(
        "authz_permissions",
        sa.Column("resource", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("code", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("resource", "action", name="uq_authz_permission_resource_action"),
    )

    op.create_table(
        "authz_role_permissions",
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("permission_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["authz_permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["authz_roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("role_id", "permission_id", name="pk_authz_role_permission"),
    )

    op.create_table(
        "authz_user_roles",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role_id", sa.String(length=36), nullable=False),
        sa.Column("scope_company_id", sa.String(length=36), nullable=True),
        sa.Column("scope_site_id", sa.String(length=36), nullable=True),
        sa.Column("scope_project_id", sa.String(length=36), nullable=True),
        sa.Column("scope_contractor_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["authz_roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_authz_user_roles_user", "authz_user_roles", ["user_id"], unique=False)
    op.create_index("ix_authz_user_roles_role", "authz_user_roles", ["role_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_authz_user_roles_role", table_name="authz_user_roles")
    op.drop_index("ix_authz_user_roles_user", table_name="authz_user_roles")
    op.drop_table("authz_user_roles")
    op.drop_table("authz_role_permissions")
    op.drop_table("authz_permissions")
    op.drop_table("authz_roles")
