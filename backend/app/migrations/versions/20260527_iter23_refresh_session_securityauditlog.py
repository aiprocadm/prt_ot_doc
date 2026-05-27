"""iter-23: add refresh_session and securityauditlog tables missing from migrations.

Revision ID: 20260527_iter23_refresh_session_securityauditlog
Revises: 20260527_iter21_user_company_id
Create Date: 2026-05-27

Cohort fix for two ``User.company_id``-class ORM↔migration drifts surfaced
by the new ``scripts/audit/check_orm_migration_drift.py`` audit tool.

Root cause:
  - ``RefreshSession`` (``backend/app/models/models.py:473`` →
    ``refresh_session`` table, used by auth refresh-token rotation)
  - ``SecurityAuditLog`` (``backend/app/models/models.py:2154`` →
    ``securityauditlog`` table, used by RBAC decision logging)

Both were added to model files without paired Alembic migrations. Tests
pass because ``Base.metadata.create_all()`` builds the schema directly
from the model side; production Postgres has the tables only by luck of
a manual DDL or schema drift, and any fresh deployment (CI perf-smoke,
new tenant) crashes the first time auth or RBAC paths run.

Surface predictions (without this fix):
  1. perf-smoke api-1 login flow → ``RefreshSessionError`` wrapping
     ``UndefinedTableError: relation "refresh_session" does not exist``
     on ``create_refresh_session()`` (auth.py:205).
  2. Any RBAC-checked request → ``UndefinedTableError`` on
     ``SecurityAuditLog`` INSERT (modules/audit/security_log.py:26).

Cohort rationale (per [[rb002-enum-migration-cohort]]):
  - Shared root cause (model-without-migration anti-pattern).
  - Shared discovery (single audit script).
  - Bundling cost < surprise-in-CI cost — landing one without the other
    just trades which of {auth, RBAC} crashes first.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_iter23_refresh_session_securityauditlog"
down_revision: str | Sequence[str] | None = "20260527_iter21_user_company_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- refresh_session ----------------------------------------------------
    op.create_table(
        "refresh_session",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("family_id", sa.String(length=36), nullable=False),
        sa.Column("token_jti", sa.String(length=64), nullable=False),
        sa.Column("parent_token_jti", sa.String(length=64), nullable=True),
        sa.Column("replaced_by_token_jti", sa.String(length=64), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_refresh_session_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], name="fk_refresh_session_user", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("token_jti", name="uq_refresh_session_token_jti"),
    )
    op.create_index(
        "ix_refresh_session_tenant_id", "refresh_session", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_refresh_session_user_id", "refresh_session", ["user_id"], unique=False
    )
    op.create_index(
        "ix_refresh_session_family_id", "refresh_session", ["family_id"], unique=False
    )
    op.create_index(
        "ix_refresh_session_token_jti", "refresh_session", ["token_jti"], unique=False
    )
    op.create_index(
        "ix_refresh_session_user_family",
        "refresh_session",
        ["tenant_id", "user_id", "family_id"],
        unique=False,
    )
    op.create_index(
        "ix_refresh_session_family_active",
        "refresh_session",
        ["tenant_id", "family_id", "revoked_at"],
        unique=False,
    )

    # --- securityauditlog ---------------------------------------------------
    op.create_table(
        "securityauditlog",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("when", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("reason_code", sa.String(length=128), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_securityauditlog_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
            name="fk_securityauditlog_user",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_securityauditlog_tenant_id", "securityauditlog", ["tenant_id"], unique=False
    )
    op.create_index(
        "ix_securityauditlog_user_id", "securityauditlog", ["user_id"], unique=False
    )
    op.create_index(
        "ix_security_auditlog_action", "securityauditlog", ["action"], unique=False
    )
    op.create_index(
        "ix_security_auditlog_decision", "securityauditlog", ["decision"], unique=False
    )
    op.create_index(
        "ix_security_auditlog_resource",
        "securityauditlog",
        ["resource_type", "resource_id"],
        unique=False,
    )
    op.create_index(
        "ix_security_auditlog_when", "securityauditlog", ["when"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_security_auditlog_when", table_name="securityauditlog")
    op.drop_index("ix_security_auditlog_resource", table_name="securityauditlog")
    op.drop_index("ix_security_auditlog_decision", table_name="securityauditlog")
    op.drop_index("ix_security_auditlog_action", table_name="securityauditlog")
    op.drop_index("ix_securityauditlog_user_id", table_name="securityauditlog")
    op.drop_index("ix_securityauditlog_tenant_id", table_name="securityauditlog")
    op.drop_table("securityauditlog")

    op.drop_index("ix_refresh_session_family_active", table_name="refresh_session")
    op.drop_index("ix_refresh_session_user_family", table_name="refresh_session")
    op.drop_index("ix_refresh_session_token_jti", table_name="refresh_session")
    op.drop_index("ix_refresh_session_family_id", table_name="refresh_session")
    op.drop_index("ix_refresh_session_user_id", table_name="refresh_session")
    op.drop_index("ix_refresh_session_tenant_id", table_name="refresh_session")
    op.drop_table("refresh_session")
