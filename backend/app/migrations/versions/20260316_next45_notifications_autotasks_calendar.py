"""next45 notifications autotasks calendar

Revision ID: 20260316_next45
Revises: 20260315_next44_search_archive_index
Create Date: 2026-03-16
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260316_next45"
down_revision = "20260315_next44_search_archive_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_channel_settings",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("email_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "telegram_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("inapp_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("telegram_chat_id", sa.String(length=255), nullable=True),
        sa.Column("quiet_hours", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", name="uq_notification_channel_settings_tenant_user"
        ),
    )

    op.create_table(
        "notifications",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("email", "telegram", "inapp", name="notificationchannel"),
            nullable=False,
        ),
        sa.Column(
            "type",
            sa.Enum(
                "JobStatusChanged",
                "DocumentGenerated",
                "DocumentExported",
                "DocumentSigned",
                "TrainingDueSoon",
                "TrainingOverdue",
                "TrainingCompleted",
                "PPEExpirySoon",
                "PPEIssueCreated",
                "MedicalDueSoon",
                "PermitExpirySoon",
                "InspectionPlanned",
                "InspectionOverdue",
                "IncidentAssigned",
                "CADueSoon",
                name="notificationtype",
            ),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "status",
            sa.Enum("queued", "sent", "failed", "canceled", "read", name="notificationstatus"),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("dedup_key", sa.String(length=255), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_queue",
        "notifications",
        ["tenant_id", "user_id", "status", "scheduled_at"],
    )
    op.create_index(
        "ix_notifications_dedup_active",
        "notifications",
        ["dedup_key"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "reminder_rules",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "entity_type",
            sa.Enum(
                "training",
                "ppe",
                "medical",
                "permit",
                "inspection",
                "incident",
                "document_job",
                "edo",
                name="reminderentitytype",
            ),
            nullable=False,
        ),
        sa.Column("date_field", sa.String(length=64), nullable=False),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recipients", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("action", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_reminder_rules_tenant_code"),
    )

    op.create_table(
        "plan_tasks",
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("assignee_id", sa.String(length=36), nullable=True),
        sa.Column(
            "status",
            sa.Enum("open", "in_progress", "done", "canceled", "overdue", name="plantaskstatus_v2"),
            nullable=False,
            server_default="open",
        ),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_plan_tasks_assignee_status_due",
        "plan_tasks",
        ["tenant_id", "assignee_id", "status", "due_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_plan_tasks_assignee_status_due", table_name="plan_tasks")
    op.drop_table("plan_tasks")
    op.drop_table("reminder_rules")
    op.drop_index("ix_notifications_dedup_active", table_name="notifications")
    op.drop_index("ix_notifications_queue", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("notification_channel_settings")

    sa.Enum(name="plantaskstatus_v2").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="reminderentitytype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationstatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationtype").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="notificationchannel").drop(op.get_bind(), checkfirst=True)
