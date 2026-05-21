"""next30 approval/signing core v1

Revision ID: 20260303_next30_approval_signing_core
Revises: 20260302_next29_files_search_v1
Create Date: 2026-03-03 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260303_next30_approval_signing_core"
down_revision = "20260302_next29"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("approval_routes", sa.Column("priority", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("approval_routes", sa.Column("conditions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("approval_routes", sa.Column("steps", sa.JSON(), nullable=False, server_default=sa.text("'[]'")))
    op.add_column("approval_routes", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    process_status = postgresql.ENUM(
        "pending", "in_progress", "approved", "rejected", "canceled", "expired",
        name="approvalprocessstatus", create_type=False,
    )
    task_status = postgresql.ENUM(
        "open", "done", "canceled", "expired",
        name="approvaltaskstatus", create_type=False,
    )
    signature_request_status = postgresql.ENUM(
        "created", "requested", "signed", "failed",
        name="signaturerequeststatus", create_type=False,
    )
    edo_envelope_status = postgresql.ENUM(
        "queued", "sent", "delivered", "signed", "rejected", "failed",
        name="edoenvelopestatus", create_type=False,
    )
    bind = op.get_bind()
    process_status.create(bind, checkfirst=True)
    task_status.create(bind, checkfirst=True)
    signature_request_status.create(bind, checkfirst=True)
    edo_envelope_status.create(bind, checkfirst=True)

    op.create_table(
        "approval_processes",
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("route_id", sa.String(length=36), nullable=False),
        sa.Column("status", process_status, nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["approval_routes.id"]),
        sa.ForeignKeyConstraint(["created_by"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_processes_status", "approval_processes", ["tenant_id", "status"])
    op.create_index("ix_approval_processes_object", "approval_processes", ["tenant_id", "object_type", "object_id"])

    op.create_table(
        "approval_tasks",
        sa.Column("process_id", sa.String(length=36), nullable=False),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("assignee_type", sa.String(length=16), nullable=False),
        sa.Column("assignee_id", sa.String(length=64), nullable=False),
        sa.Column("status", task_status, nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delegated_from", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["process_id"], ["approval_processes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_tasks_status", "approval_tasks", ["tenant_id", "status"])
    op.create_index("ix_approval_tasks_assignee", "approval_tasks", ["tenant_id", "assignee_type", "assignee_id"])

    op.create_table(
        "approval_decision_logs",
        sa.Column("process_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("step_no", sa.Integer(), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["process_id"], ["approval_processes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["approval_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "signature_requests",
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", signature_request_status, nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signature_requests_status", "signature_requests", ["tenant_id", "status"])
    op.create_index("ix_signature_requests_object", "signature_requests", ["tenant_id", "object_type", "object_id"])

    op.create_table(
        "edo_envelopes",
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("object_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", edo_envelope_status, nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_edo_envelopes_status", "edo_envelopes", ["tenant_id", "status"])
    op.create_index("ix_edo_envelopes_object", "edo_envelopes", ["tenant_id", "object_type", "object_id"])


def downgrade() -> None:
    op.drop_index("ix_edo_envelopes_object", table_name="edo_envelopes")
    op.drop_index("ix_edo_envelopes_status", table_name="edo_envelopes")
    op.drop_table("edo_envelopes")
    op.drop_index("ix_signature_requests_object", table_name="signature_requests")
    op.drop_index("ix_signature_requests_status", table_name="signature_requests")
    op.drop_table("signature_requests")
    op.drop_table("approval_decision_logs")
    op.drop_index("ix_approval_tasks_assignee", table_name="approval_tasks")
    op.drop_index("ix_approval_tasks_status", table_name="approval_tasks")
    op.drop_table("approval_tasks")
    op.drop_index("ix_approval_processes_object", table_name="approval_processes")
    op.drop_index("ix_approval_processes_status", table_name="approval_processes")
    op.drop_table("approval_processes")

    op.drop_column("approval_routes", "deleted_at")
    op.drop_column("approval_routes", "steps")
    op.drop_column("approval_routes", "conditions")
    op.drop_column("approval_routes", "priority")

    bind = op.get_bind()
    sa.Enum(name="edoenvelopestatus").drop(bind, checkfirst=True)
    sa.Enum(name="signaturerequeststatus").drop(bind, checkfirst=True)
    sa.Enum(name="approvaltaskstatus").drop(bind, checkfirst=True)
    sa.Enum(name="approvalprocessstatus").drop(bind, checkfirst=True)
