"""Add approval/signature/edo workflow entities.

Revision ID: 20250425_edo_approval_signature_mvp
Revises: 20250420_p1_obligations_inspections_attestations
Create Date: 2025-04-25 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250425_edo_approval_signature_mvp"
down_revision: str | tuple[str, ...] = "20250420_p1_obligations_inspections_attestations"
branch_labels: str | None = None
depends_on: str | None = None

approval_request_status = postgresql.ENUM(
    "draft", "running", "approved", "rejected", "canceled",
    name="approvalrequeststatus", create_type=False,
)
approval_decision_type = postgresql.ENUM(
    "approve", "reject", "delegate", name="approvaldecisiontype", create_type=False,
)
signature_type = postgresql.ENUM(
    "KEP", "UNEP", "INTERNAL", name="signaturetype", create_type=False,
)
signature_status = postgresql.ENUM(
    "pending", "signed", "failed", name="signaturestatus", create_type=False,
)
edo_direction = postgresql.ENUM(
    "outgoing", "incoming", name="edodirection", create_type=False,
)
edo_status = postgresql.ENUM(
    "queued", "sent", "delivered", "accepted", "rejected", "failed",
    name="edostatus", create_type=False,
)


def upgrade() -> None:
    bind = op.get_bind()
    approval_request_status.create(bind, checkfirst=True)
    approval_decision_type.create(bind, checkfirst=True)
    signature_type.create(bind, checkfirst=True)
    signature_status.create(bind, checkfirst=True)
    edo_direction.create(bind, checkfirst=True)
    edo_status.create(bind, checkfirst=True)

    op.create_table(
        "approval_routes",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("rules_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", "version", name="uq_approval_route_code_version"),
    )
    op.create_index("ix_approval_routes_code", "approval_routes", ["tenant_id", "code"])

    op.create_table(
        "approval_requests",
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("route_id", sa.String(length=36), nullable=False),
        sa.Column("status", approval_request_status, nullable=False),
        sa.Column("current_step_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["documentversion.id"]),
        sa.ForeignKeyConstraint(["route_id"], ["approval_routes.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_status", "approval_requests", ["tenant_id", "status"])
    op.create_index("ix_approval_requests_created", "approval_requests", ["tenant_id", "created_at"])

    op.create_table(
        "approval_decisions",
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=False),
        sa.Column("decision", approval_decision_type, nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["request_id"], ["approval_requests.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "signatures",
        sa.Column("document_version_id", sa.String(length=36), nullable=False),
        sa.Column("type", signature_type, nullable=False),
        sa.Column("status", signature_status, nullable=False),
        sa.Column("signer_user_id", sa.String(length=36), nullable=True),
        sa.Column("cert_info_json", sa.JSON(), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("receipts_s3_key", sa.String(length=512), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["documentversion.id"]),
        sa.ForeignKeyConstraint(["signer_user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signatures_document", "signatures", ["tenant_id", "document_version_id"])
    op.create_index("ix_signatures_status", "signatures", ["tenant_id", "status"])

    op.create_table(
        "edo_messages",
        sa.Column("direction", edo_direction, nullable=False),
        sa.Column("document_version_id", sa.String(length=36), nullable=True),
        sa.Column("provider_code", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("status", edo_status, nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_version_id"], ["documentversion.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edo_messages_created", "edo_messages", ["tenant_id", "created_at"])
    op.create_index("ix_edo_messages_provider_external", "edo_messages", ["tenant_id", "provider_code", "external_id"])

    op.create_table(
        "edo_receipts",
        sa.Column("edo_message_id", sa.String(length=36), nullable=False),
        sa.Column("receipt_type", sa.String(length=64), nullable=False),
        sa.Column("s3_key", sa.String(length=512), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["edo_message_id"], ["edo_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "edo_status_history",
        sa.Column("edo_message_id", sa.String(length=36), nullable=False),
        sa.Column("status", edo_status, nullable=False),
        sa.Column("raw_payload_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["edo_message_id"], ["edo_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("edo_status_history")
    op.drop_table("edo_receipts")
    op.drop_index("ix_edo_messages_provider_external", table_name="edo_messages")
    op.drop_index("ix_edo_messages_created", table_name="edo_messages")
    op.drop_table("edo_messages")
    op.drop_index("ix_signatures_status", table_name="signatures")
    op.drop_index("ix_signatures_document", table_name="signatures")
    op.drop_table("signatures")
    op.drop_table("approval_decisions")
    op.drop_index("ix_approval_requests_created", table_name="approval_requests")
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_approval_routes_code", table_name="approval_routes")
    op.drop_table("approval_routes")

    bind = op.get_bind()
    edo_status.drop(bind, checkfirst=True)
    edo_direction.drop(bind, checkfirst=True)
    signature_status.drop(bind, checkfirst=True)
    signature_type.drop(bind, checkfirst=True)
    approval_decision_type.drop(bind, checkfirst=True)
    approval_request_status.drop(bind, checkfirst=True)
