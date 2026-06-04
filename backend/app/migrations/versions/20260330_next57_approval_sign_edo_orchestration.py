"""next57 approval sign edo orchestration

Revision ID: 20260330_next57
Revises: 20260329_next56_pack_runs_and_presets
Create Date: 2026-03-30 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "20260330_next57"
down_revision = "20260329_next56"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documentversion", sa.Column("approval_status", sa.Text(), nullable=True))
    op.add_column("documentversion", sa.Column("signature_status", sa.Text(), nullable=True))
    op.add_column("documentversion", sa.Column("edo_status", sa.Text(), nullable=True))
    op.add_column("documentversion", sa.Column("released_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column("pack_runs", sa.Column("approval_status", sa.Text(), nullable=True))
    op.add_column("pack_runs", sa.Column("signature_status", sa.Text(), nullable=True))
    op.add_column("pack_runs", sa.Column("edo_status", sa.Text(), nullable=True))

    op.create_table(
        "approval_route_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("approval_route_id", sa.String(length=36), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(length=16), nullable=False),
        sa.Column("role_code", sa.String(length=128), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("can_delegate", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("deadline_hours", sa.Integer(), nullable=True),
        sa.Column("escalation_role_code", sa.String(length=128), nullable=True),
        sa.Column("escalation_user_id", sa.String(length=36), nullable=True),
        sa.Column("conditions_json", sa.JSON(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["approval_route_id"], ["approval_routes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_route_id", "order_no", name="uq_approval_route_steps_order"),
    )

    op.create_table(
        "approval_instances",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=16), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("approval_route_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_by", sa.String(length=36), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_step_no", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["approval_route_id"], ["approval_routes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "approval_instance_steps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("approval_instance_id", sa.String(length=36), nullable=False),
        sa.Column("route_step_id", sa.String(length=36), nullable=False),
        sa.Column("order_no", sa.Integer(), nullable=False),
        sa.Column("assignee_user_id", sa.String(length=36), nullable=True),
        sa.Column("assignee_role_code", sa.String(length=128), nullable=True),
        sa.Column("delegated_from_user_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_instance_id"], ["approval_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_step_id"], ["approval_route_steps.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "edo_status_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("edo_message_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["edo_message_id"], ["edo_messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "edo_webhook_inbox",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("operator_code", sa.String(length=64), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=True),
        sa.Column("dedupe_key", sa.String(length=255), nullable=False),
        sa.Column("headers_json", sa.JSON(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key", name="uq_edo_webhook_inbox_dedupe_key"),
    )

    # iter-15: add_columns MUST precede create_indexes — Postgres rejects
    # CREATE INDEX referencing a column that does not yet exist, even though
    # SQLite's looser model tolerated the original order. ix_edo_messages_
    # entity_status_created below depends on entity_type/entity_id which are
    # added to edo_messages a few lines down. Moving all add_columns above
    # all create_indexes keeps the schema-change vs index-rebuild phases
    # clearly separated and avoids re-introducing the same class of bug for
    # later columns added to the same tables.
    op.add_column("approval_routes", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("approval_routes", sa.Column("applies_to", sa.String(length=16), nullable=False, server_default="document"))
    op.add_column("approval_routes", sa.Column("conditions_json", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("approval_routes", sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("approval_routes", sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"))

    op.add_column("signature_requests", sa.Column("requested_by", sa.String(length=36), nullable=True))
    op.add_column("signature_requests", sa.Column("approval_instance_id", sa.String(length=36), nullable=True))
    op.add_column("signature_requests", sa.Column("signature_type", sa.String(length=16), nullable=False, server_default="kep"))
    op.add_column("signature_requests", sa.Column("provider_code", sa.String(length=64), nullable=True))
    op.add_column("signature_requests", sa.Column("external_request_id", sa.String(length=255), nullable=True))
    op.add_column("signature_requests", sa.Column("certificate_thumbprint", sa.String(length=255), nullable=True))
    op.add_column("signature_requests", sa.Column("signer_name", sa.String(length=255), nullable=True))
    op.add_column("signature_requests", sa.Column("signed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("signature_requests", sa.Column("verification_result_json", sa.JSON(), nullable=True))

    op.add_column("edo_messages", sa.Column("entity_type", sa.String(length=16), nullable=True))
    op.add_column("edo_messages", sa.Column("entity_id", sa.String(length=36), nullable=True))
    op.add_column("edo_messages", sa.Column("operator_code", sa.String(length=64), nullable=True))
    op.add_column("edo_messages", sa.Column("message_type", sa.String(length=64), nullable=True))
    op.add_column("edo_messages", sa.Column("external_message_id", sa.String(length=255), nullable=True))
    op.add_column("edo_messages", sa.Column("external_thread_id", sa.String(length=255), nullable=True))
    op.add_column("edo_messages", sa.Column("roaming_status", sa.String(length=64), nullable=True))
    op.add_column("edo_messages", sa.Column("last_status_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("edo_messages", sa.Column("request_payload_json", sa.JSON(), nullable=True))
    op.add_column("edo_messages", sa.Column("response_payload_json", sa.JSON(), nullable=True))
    op.add_column("edo_messages", sa.Column("protocol_file_id", sa.String(length=36), nullable=True))
    op.add_column("edo_messages", sa.Column("created_by", sa.String(length=36), nullable=True))

    op.create_index("ix_approval_instances_entity", "approval_instances", ["tenant_id", "entity_type", "entity_id"])
    op.create_index("ix_approval_instance_steps_lookup", "approval_instance_steps", ["approval_instance_id", "status", "order_no"])
    op.create_index("ix_signature_requests_entity_status", "signature_requests", ["tenant_id", "object_type", "object_id", "status"])
    op.create_index("ix_edo_messages_entity_status_created", "edo_messages", ["tenant_id", "entity_type", "entity_id", "status", "created_at"])
    op.create_index("ix_edo_status_events_message_received", "edo_status_events", ["edo_message_id", "received_at"])


def downgrade() -> None:
    # Drop indexes BEFORE the columns/tables they span. Postgres auto-drops an
    # index when a column it covers is dropped, so the original order
    # (drop_column first) made the later drop_index raise "index ... does not
    # exist" — e.g. ix_edo_messages_entity_status_created spans entity_type /
    # entity_id, dropped just below. Mirrors upgrade(), which deliberately
    # creates these indexes only AFTER the add_column calls.
    op.drop_index("ix_edo_status_events_message_received", table_name="edo_status_events")
    op.drop_index("ix_edo_messages_entity_status_created", table_name="edo_messages")
    op.drop_index("ix_signature_requests_entity_status", table_name="signature_requests")
    op.drop_index("ix_approval_instance_steps_lookup", table_name="approval_instance_steps")
    op.drop_index("ix_approval_instances_entity", table_name="approval_instances")

    op.drop_column("edo_messages", "created_by")
    op.drop_column("edo_messages", "protocol_file_id")
    op.drop_column("edo_messages", "response_payload_json")
    op.drop_column("edo_messages", "request_payload_json")
    op.drop_column("edo_messages", "last_status_at")
    op.drop_column("edo_messages", "roaming_status")
    op.drop_column("edo_messages", "external_thread_id")
    op.drop_column("edo_messages", "external_message_id")
    op.drop_column("edo_messages", "message_type")
    op.drop_column("edo_messages", "operator_code")
    op.drop_column("edo_messages", "entity_id")
    op.drop_column("edo_messages", "entity_type")

    op.drop_column("signature_requests", "verification_result_json")
    op.drop_column("signature_requests", "signed_at")
    op.drop_column("signature_requests", "signer_name")
    op.drop_column("signature_requests", "certificate_thumbprint")
    op.drop_column("signature_requests", "external_request_id")
    op.drop_column("signature_requests", "provider_code")
    op.drop_column("signature_requests", "signature_type")
    op.drop_column("signature_requests", "approval_instance_id")
    op.drop_column("signature_requests", "requested_by")

    op.drop_column("approval_routes", "status")
    op.drop_column("approval_routes", "is_default")
    op.drop_column("approval_routes", "conditions_json")
    op.drop_column("approval_routes", "applies_to")
    op.drop_column("approval_routes", "description")

    op.drop_table("edo_webhook_inbox")
    op.drop_table("edo_status_events")
    op.drop_table("approval_instance_steps")
    op.drop_table("approval_instances")
    op.drop_table("approval_route_steps")

    op.drop_column("pack_runs", "edo_status")
    op.drop_column("pack_runs", "signature_status")
    op.drop_column("pack_runs", "approval_status")

    op.drop_column("documentversion", "released_at")
    op.drop_column("documentversion", "edo_status")
    op.drop_column("documentversion", "signature_status")
    op.drop_column("documentversion", "approval_status")
