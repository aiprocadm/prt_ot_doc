"""next46 training briefings offline

Revision ID: 20260317_next46
Revises: 20260316_next45
Create Date: 2026-03-17
"""

import sqlalchemy as sa
from alembic import op

revision = "20260317_next46"
down_revision = "20260316_next45"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
    ]


def _create_soft_table(name: str, *columns: sa.Column, unique: tuple[str, ...] | None = None) -> None:
    args = list(columns) + _base_columns() + [sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)]
    constraints: list[sa.Constraint] = [sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]), sa.PrimaryKeyConstraint("id")]
    if unique is not None:
        constraints.append(sa.UniqueConstraint(*unique, name=f"uq_{name}_{'_'.join(unique[1:])}"))
    op.create_table(name, *args, *constraints)


def _create_table(name: str, *columns: sa.Column) -> None:
    op.create_table(
        name,
        *columns,
        *_base_columns(),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    _create_soft_table(
        "training_programs",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("duration_hours", sa.Numeric(8, 2), nullable=True),
        sa.Column("validity_months", sa.Integer(), nullable=True),
        sa.Column("external_registry_type", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_user_id", sa.String(length=36), nullable=True),
        unique=("tenant_id", "code"),
    )
    _create_table(
        "training_modules",
        sa.Column("training_program_id", sa.String(length=36), sa.ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("module_order", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("content_ref", sa.Text(), nullable=True),
        sa.Column("required", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    _create_soft_table(
        "training_tests",
        sa.Column("training_program_id", sa.String(length=36), sa.ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("passing_score", sa.Integer(), nullable=False),
        sa.Column("time_limit_minutes", sa.Integer(), nullable=True),
        sa.Column("attempts_limit", sa.Integer(), nullable=True),
        sa.Column("randomize_questions", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    _create_table(
        "training_test_questions",
        sa.Column("training_test_id", sa.String(length=36), sa.ForeignKey("training_tests.id", ondelete="CASCADE"), nullable=False),
        sa.Column("question_order", sa.Integer(), nullable=False),
        sa.Column("question_type", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("correct_answer_json", sa.JSON(), nullable=True),
        sa.Column("weight", sa.Numeric(8, 2), nullable=False, server_default="1"),
    )
    _create_soft_table(
        "training_groups",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("training_program_id", sa.String(length=36), sa.ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("teacher_user_id", sa.String(length=36), nullable=True),
        sa.Column("planned_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("planned_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("site_id", sa.String(length=36), sa.ForeignKey("site.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company_id", sa.String(length=36), sa.ForeignKey("company.id", ondelete="SET NULL"), nullable=True),
        unique=("tenant_id", "code"),
    )
    _create_soft_table(
        "training_protocols",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("training_program_id", sa.String(length=36), sa.ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("training_group_id", sa.String(length=36), sa.ForeignKey("training_groups.id", ondelete="SET NULL"), nullable=True),
        sa.Column("protocol_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("file_id", sa.String(length=36), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_by", sa.String(length=36), nullable=True),
        unique=("tenant_id", "code"),
    )
    _create_soft_table(
        "training_certificates",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("training_program_id", sa.String(length=36), sa.ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("person_id", sa.String(length=36), sa.ForeignKey("person.id", ondelete="SET NULL"), nullable=True),
        sa.Column("issued_at", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("file_id", sa.String(length=36), sa.ForeignKey("file.id", ondelete="SET NULL"), nullable=True),
        sa.Column("external_registry_status", sa.Text(), nullable=True),
        sa.Column("external_registry_payload", sa.JSON(), nullable=True),
        unique=("tenant_id", "code"),
    )
    _create_soft_table(
        "briefing_templates",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("briefing_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("validity_days", sa.Integer(), nullable=True),
        unique=("tenant_id", "code"),
    )
    _create_soft_table(
        "briefing_journals",
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("site_id", sa.String(length=36), sa.ForeignKey("site.id", ondelete="SET NULL"), nullable=True),
        sa.Column("department_id", sa.String(length=36), sa.ForeignKey("department.id", ondelete="SET NULL"), nullable=True),
        sa.Column("journal_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        unique=("tenant_id", "code"),
    )

    _create_table("training_enrollments", sa.Column("training_group_id", sa.String(36), sa.ForeignKey("training_groups.id", ondelete="SET NULL")), sa.Column("training_program_id", sa.String(36), sa.ForeignKey("training_programs.id", ondelete="CASCADE"), nullable=False), sa.Column("person_id", sa.String(36), sa.ForeignKey("person.id", ondelete="SET NULL")), sa.Column("assigned_by_user_id", sa.String(36)), sa.Column("assignment_source", sa.Text(), nullable=False), sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False), sa.Column("due_at", sa.DateTime(timezone=True)), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("expires_at", sa.DateTime(timezone=True)), sa.Column("status", sa.Text(), nullable=False), sa.Column("score", sa.Numeric(8, 2)), sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("certificate_id", sa.String(36), sa.ForeignKey("training_certificates.id", ondelete="SET NULL")), sa.Column("protocol_id", sa.String(36), sa.ForeignKey("training_protocols.id", ondelete="SET NULL")), sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    _create_table("training_attempts", sa.Column("training_enrollment_id", sa.String(36), sa.ForeignKey("training_enrollments.id", ondelete="CASCADE"), nullable=False), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("submitted_at", sa.DateTime(timezone=True)), sa.Column("score", sa.Numeric(8, 2)), sa.Column("passed", sa.Boolean()), sa.Column("answers_json", sa.JSON()))
    _create_table("training_protocol_items", sa.Column("training_protocol_id", sa.String(36), sa.ForeignKey("training_protocols.id", ondelete="CASCADE"), nullable=False), sa.Column("person_id", sa.String(36), sa.ForeignKey("person.id", ondelete="SET NULL")), sa.Column("fio_text", sa.Text()), sa.Column("result", sa.Text(), nullable=False), sa.Column("score", sa.Numeric(8, 2)), sa.Column("enrollment_id", sa.String(36), sa.ForeignKey("training_enrollments.id", ondelete="SET NULL")))
    _create_table("briefing_entries", sa.Column("briefing_journal_id", sa.String(36), sa.ForeignKey("briefing_journals.id", ondelete="CASCADE"), nullable=False), sa.Column("briefing_template_id", sa.String(36), sa.ForeignKey("briefing_templates.id", ondelete="SET NULL")), sa.Column("person_id", sa.String(36), sa.ForeignKey("person.id", ondelete="SET NULL")), sa.Column("instructor_user_id", sa.String(36)), sa.Column("site_id", sa.String(36), sa.ForeignKey("site.id", ondelete="SET NULL")), sa.Column("department_id", sa.String(36), sa.ForeignKey("department.id", ondelete="SET NULL")), sa.Column("workplace_id", sa.String(36), sa.ForeignKey("workplace.id", ondelete="SET NULL")), sa.Column("briefing_type", sa.Text(), nullable=False), sa.Column("briefing_date", sa.DateTime(timezone=True), nullable=False), sa.Column("valid_until", sa.DateTime(timezone=True)), sa.Column("reason", sa.Text()), sa.Column("status", sa.Text(), nullable=False), sa.Column("notes", sa.Text()), sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    _create_table("briefing_signatures", sa.Column("briefing_entry_id", sa.String(36), sa.ForeignKey("briefing_entries.id", ondelete="CASCADE"), nullable=False), sa.Column("signer_type", sa.Text(), nullable=False), sa.Column("signer_user_id", sa.String(36)), sa.Column("signer_person_id", sa.String(36), sa.ForeignKey("person.id", ondelete="SET NULL")), sa.Column("signature_mode", sa.Text(), nullable=False), sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False), sa.Column("signature_payload", sa.JSON()))

    _create_table("training_plans", sa.Column("code", sa.Text(), nullable=False), sa.Column("title", sa.Text(), nullable=False), sa.Column("period_start", sa.Date(), nullable=False), sa.Column("period_end", sa.Date(), nullable=False), sa.Column("status", sa.Text(), nullable=False), sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_unique_constraint("uq_training_plans_tenant_code", "training_plans", ["tenant_id", "code"])
    _create_table("training_plan_items", sa.Column("training_plan_id", sa.String(36), sa.ForeignKey("training_plans.id", ondelete="CASCADE"), nullable=False), sa.Column("person_id", sa.String(36), sa.ForeignKey("person.id", ondelete="SET NULL")), sa.Column("position_id", sa.String(36), sa.ForeignKey("position.id", ondelete="SET NULL")), sa.Column("site_id", sa.String(36), sa.ForeignKey("site.id", ondelete="SET NULL")), sa.Column("training_program_id", sa.String(36), sa.ForeignKey("training_programs.id", ondelete="SET NULL")), sa.Column("briefing_template_id", sa.String(36), sa.ForeignKey("briefing_templates.id", ondelete="SET NULL")), sa.Column("planned_for", sa.Date(), nullable=False), sa.Column("due_at", sa.Date()), sa.Column("priority", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False))
    _create_table("compliance_deadlines", sa.Column("entity_type", sa.Text(), nullable=False), sa.Column("entity_id", sa.String(36), nullable=False), sa.Column("person_id", sa.String(36), sa.ForeignKey("person.id", ondelete="SET NULL")), sa.Column("site_id", sa.String(36), sa.ForeignKey("site.id", ondelete="SET NULL")), sa.Column("due_at", sa.DateTime(timezone=True), nullable=False), sa.Column("status", sa.Text(), nullable=False), sa.Column("reminder_policy", sa.Text()))
    _create_table("calendar_events", sa.Column("source_type", sa.Text(), nullable=False), sa.Column("source_id", sa.String(36), nullable=False), sa.Column("title", sa.Text(), nullable=False), sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False), sa.Column("ends_at", sa.DateTime(timezone=True)), sa.Column("site_id", sa.String(36), sa.ForeignKey("site.id", ondelete="SET NULL")), sa.Column("assigned_user_id", sa.String(36)), sa.Column("status", sa.Text(), nullable=False))
    _create_table("offline_sync_batches", sa.Column("user_id", sa.String(36), nullable=False), sa.Column("device_id", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False), sa.Column("entity_type", sa.Text(), nullable=False), sa.Column("payload", sa.JSON(), nullable=False), sa.Column("error_payload", sa.JSON()))
    _create_table("offline_media_queue", sa.Column("user_id", sa.String(36), nullable=False), sa.Column("device_id", sa.Text(), nullable=False), sa.Column("local_ref", sa.Text(), nullable=False), sa.Column("file_id", sa.String(36), sa.ForeignKey("file.id", ondelete="SET NULL")), sa.Column("upload_status", sa.Text(), nullable=False), sa.Column("metadata_json", sa.JSON()))
    _create_table("external_registry_jobs", sa.Column("entity_type", sa.Text(), nullable=False), sa.Column("entity_id", sa.String(36), nullable=False), sa.Column("registry_type", sa.Text(), nullable=False), sa.Column("status", sa.Text(), nullable=False), sa.Column("request_payload", sa.JSON()), sa.Column("response_payload", sa.JSON()))

    op.create_index("ix_training_enrollments_person", "training_enrollments", ["tenant_id", "person_id", "status", "due_at", "expires_at"])
    op.create_index("ix_training_certificates_person", "training_certificates", ["tenant_id", "person_id", "status", "valid_until"])
    op.create_index("ix_briefing_entries_person", "briefing_entries", ["tenant_id", "person_id", "briefing_type", "briefing_date"])
    op.create_index("ix_compliance_deadlines_due", "compliance_deadlines", ["tenant_id", "status", "due_at"])
    op.create_index("ix_calendar_events_starts", "calendar_events", ["tenant_id", "starts_at", "assigned_user_id"])
    op.create_index("ix_offline_sync_batches_status", "offline_sync_batches", ["tenant_id", "user_id", "status", "created_at"])


def downgrade() -> None:
    for idx, table in [
        ("ix_offline_sync_batches_status", "offline_sync_batches"),
        ("ix_calendar_events_starts", "calendar_events"),
        ("ix_compliance_deadlines_due", "compliance_deadlines"),
        ("ix_briefing_entries_person", "briefing_entries"),
        ("ix_training_certificates_person", "training_certificates"),
        ("ix_training_enrollments_person", "training_enrollments"),
    ]:
        op.drop_index(idx, table_name=table)

    for table in [
        "external_registry_jobs",
        "offline_media_queue",
        "offline_sync_batches",
        "calendar_events",
        "compliance_deadlines",
        "training_plan_items",
        "training_plans",
        "briefing_signatures",
        "briefing_entries",
        "briefing_journals",
        "briefing_templates",
        "training_protocol_items",
        "training_attempts",
        "training_enrollments",
        "training_certificates",
        "training_protocols",
        "training_groups",
        "training_test_questions",
        "training_tests",
        "training_modules",
        "training_programs",
    ]:
        op.drop_table(table)
