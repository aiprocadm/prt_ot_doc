"""notification templates foundation

Revision ID: 20260418_next66_notifications_templates_foundation
Revises: 20260410_next65_search_memory
Create Date: 2026-04-18 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260418_next66_notifications_templates_foundation"
down_revision = "20260410_next65_search_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    channel_enum = sa.Enum("email", "telegram", "inapp", "webhook", name="notificationtemplatechannel")
    type_enum = sa.Enum(
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
        "ApprovalDeadline",
        "MedicalOverdue",
        "PPEOverdue",
        "IncidentCreated",
        "InspectionCreated",
        "PrescriptionOverdue",
        "PackageRunCompleted",
        "PackageRunFailed",
        "IntegrationError",
        "EdoStatusChanged",
        "BillingLimitWarning",
        name="notificationtemplatetype",
    )
    bind = op.get_bind()
    channel_enum.create(bind, checkfirst=True)
    type_enum.create(bind, checkfirst=True)

    op.create_table(
        "notification_templates",
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("channel", channel_enum, nullable=False),
        sa.Column("type", type_enum, nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False, server_default="ru"),
        sa.Column("subject_template", sa.String(length=255), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("title_template", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("variables_schema", sa.JSON(), nullable=True),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", "channel", "locale", name="uq_notification_templates_scope"),
    )
    op.create_index("ix_notification_templates_lookup", "notification_templates", ["tenant_id", "channel", "type", "is_active"])
    op.create_index(op.f("ix_notification_templates_tenant_id"), "notification_templates", ["tenant_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_notification_templates_tenant_id"), table_name="notification_templates")
    op.drop_index("ix_notification_templates_lookup", table_name="notification_templates")
    op.drop_table("notification_templates")
    bind = op.get_bind()
    sa.Enum(name="notificationtemplatetype").drop(bind, checkfirst=True)
    sa.Enum(name="notificationtemplatechannel").drop(bind, checkfirst=True)
