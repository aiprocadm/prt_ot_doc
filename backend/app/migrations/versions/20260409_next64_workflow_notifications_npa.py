"""workflow, notifications center, and NPA impact foundations

Revision ID: 20260409_next64
Revises: 20260408_next63_expand_alembic_version_num
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260409_next64"
down_revision: Union[str, None] = "20260408_next63_expand_alembic_version_num"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflow_definitions",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("current_version_id", sa.String(length=36), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_workflow_definition_tenant_code"),
    )
    op.create_index(
        "ix_workflow_definition_tenant_entity",
        "workflow_definitions",
        ["tenant_id", "entity_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_definitions_tenant_id"),
        "workflow_definitions",
        ["tenant_id"],
        unique=False,
    )

    workflow_definition_status = postgresql.ENUM(
        "draft",
        "published",
        "archived",
        name="workflowdefinitionstatus",
        create_type=False,
    )
    workflow_definition_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "workflow_definition_versions",
        sa.Column("definition_id", sa.String(length=36), nullable=False),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("status", workflow_definition_status, nullable=False),
        sa.Column("graph_json", sa.JSON(), nullable=False),
        sa.Column("variables_schema", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["definition_id"], ["workflow_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "definition_id", "version_no", name="uq_workflow_definition_version"
        ),
    )
    op.create_index(
        "ix_workflow_definition_version_tenant_status",
        "workflow_definition_versions",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_definition_versions_definition_id"),
        "workflow_definition_versions",
        ["definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_definition_versions_tenant_id"),
        "workflow_definition_versions",
        ["tenant_id"],
        unique=False,
    )

    workflow_instance_status = postgresql.ENUM(
        "running",
        "waiting",
        "completed",
        "failed",
        "canceled",
        name="workflowinstancestatus",
        create_type=False,
    )
    workflow_instance_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "workflow_instances",
        sa.Column("definition_id", sa.String(length=36), nullable=False),
        sa.Column("definition_version_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("status", workflow_instance_status, nullable=False),
        sa.Column("current_node_id", sa.String(length=128), nullable=True),
        sa.Column("started_by", sa.String(length=36), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(length=128), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["definition_id"], ["workflow_definitions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["definition_version_id"], ["workflow_definition_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_instance_tenant_entity",
        "workflow_instances",
        ["tenant_id", "entity_type", "entity_id"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_instance_tenant_status",
        "workflow_instances",
        ["tenant_id", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_instances_definition_id"),
        "workflow_instances",
        ["definition_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_instances_definition_version_id"),
        "workflow_instances",
        ["definition_version_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_instances_tenant_id"), "workflow_instances", ["tenant_id"], unique=False
    )

    workflow_task_status = postgresql.ENUM(
        "open",
        "completed",
        "reassigned",
        "delegated",
        "escalated",
        "canceled",
        name="workflowtaskstatus",
        create_type=False,
    )
    workflow_task_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "workflow_tasks",
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("assignee_user_id", sa.String(length=36), nullable=True),
        sa.Column("assignee_role_code", sa.String(length=64), nullable=True),
        sa.Column("status", workflow_task_status, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delegated_from_user_id", sa.String(length=36), nullable=True),
        sa.Column("task_payload", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["instance_id"], ["workflow_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_task_tenant_assignee_status",
        "workflow_tasks",
        ["tenant_id", "assignee_user_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_workflow_task_tenant_role_status",
        "workflow_tasks",
        ["tenant_id", "assignee_role_code", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_tasks_instance_id"), "workflow_tasks", ["instance_id"], unique=False
    )
    op.create_index(
        op.f("ix_workflow_tasks_tenant_id"), "workflow_tasks", ["tenant_id"], unique=False
    )

    op.create_table(
        "workflow_timeline_events",
        sa.Column("instance_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["instance_id"], ["workflow_instances.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_timeline_tenant_instance_created",
        "workflow_timeline_events",
        ["tenant_id", "instance_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_timeline_events_instance_id"),
        "workflow_timeline_events",
        ["instance_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_timeline_events_tenant_id"),
        "workflow_timeline_events",
        ["tenant_id"],
        unique=False,
    )

    notification_priority = postgresql.ENUM(
        "low",
        "medium",
        "high",
        "critical",
        name="notificationpriority",
        create_type=False,
    )
    notification_priority.create(op.get_bind(), checkfirst=True)
    with op.batch_alter_table("notification_channel_settings") as batch:
        batch.add_column(sa.Column("digest_mode", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("channel_preferences", sa.JSON(), nullable=True))
    with op.batch_alter_table("notifications") as batch:
        batch.add_column(
            sa.Column("priority", notification_priority, nullable=False, server_default="medium")
        )
    op.create_table(
        "npa_revision",
        sa.Column("act_id", sa.String(length=36), nullable=False),
        sa.Column("revision_code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["act_id"], ["npa_act.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("act_id", "revision_code", name="uq_npa_revision_per_act"),
    )
    op.create_index(op.f("ix_npa_revision_act_id"), "npa_revision", ["act_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_npa_revision_act_id"), table_name="npa_revision")
    op.drop_table("npa_revision")
    with op.batch_alter_table("notifications") as batch:
        batch.drop_column("priority")
    with op.batch_alter_table("notification_channel_settings") as batch:
        batch.drop_column("channel_preferences")
        batch.drop_column("digest_mode")
    sa.Enum(name="notificationpriority").drop(op.get_bind(), checkfirst=True)
    op.drop_index(
        op.f("ix_workflow_timeline_events_tenant_id"), table_name="workflow_timeline_events"
    )
    op.drop_index(
        op.f("ix_workflow_timeline_events_instance_id"), table_name="workflow_timeline_events"
    )
    op.drop_index(
        "ix_workflow_timeline_tenant_instance_created", table_name="workflow_timeline_events"
    )
    op.drop_table("workflow_timeline_events")
    op.drop_index(op.f("ix_workflow_tasks_tenant_id"), table_name="workflow_tasks")
    op.drop_index(op.f("ix_workflow_tasks_instance_id"), table_name="workflow_tasks")
    op.drop_index("ix_workflow_task_tenant_role_status", table_name="workflow_tasks")
    op.drop_index("ix_workflow_task_tenant_assignee_status", table_name="workflow_tasks")
    op.drop_table("workflow_tasks")
    sa.Enum(name="workflowtaskstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f("ix_workflow_instances_tenant_id"), table_name="workflow_instances")
    op.drop_index(
        op.f("ix_workflow_instances_definition_version_id"), table_name="workflow_instances"
    )
    op.drop_index(op.f("ix_workflow_instances_definition_id"), table_name="workflow_instances")
    op.drop_index("ix_workflow_instance_tenant_status", table_name="workflow_instances")
    op.drop_index("ix_workflow_instance_tenant_entity", table_name="workflow_instances")
    op.drop_table("workflow_instances")
    sa.Enum(name="workflowinstancestatus").drop(op.get_bind(), checkfirst=True)
    op.drop_index(
        op.f("ix_workflow_definition_versions_tenant_id"), table_name="workflow_definition_versions"
    )
    op.drop_index(
        op.f("ix_workflow_definition_versions_definition_id"),
        table_name="workflow_definition_versions",
    )
    op.drop_index(
        "ix_workflow_definition_version_tenant_status", table_name="workflow_definition_versions"
    )
    op.drop_table("workflow_definition_versions")
    sa.Enum(name="workflowdefinitionstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_index(op.f("ix_workflow_definitions_tenant_id"), table_name="workflow_definitions")
    op.drop_index("ix_workflow_definition_tenant_entity", table_name="workflow_definitions")
    op.drop_table("workflow_definitions")
