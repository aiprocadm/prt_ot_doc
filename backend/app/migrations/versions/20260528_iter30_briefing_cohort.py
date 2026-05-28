"""iter-30: add briefing-cohort tables missing from migrations.

Revision ID: 20260528_iter30_briefing_cohort
Revises: 20260528_iter29_version_retrofit
Create Date: 2026-05-28

Cohort fix for four ``critical`` ORM↔migration drifts surfaced by
``scripts/audit/version_column_drift.py`` (and corroborated by the
heavyweight ``check_orm_migration_drift.py`` — both flag these 4 as
having zero ``op.create_table`` matches across the migration tree).

Bug class: ORM-Migration drift, **flavor (a)** "table truly absent"
(per [[orm-migration-drift-classes]]). All four models are declared in
``backend/app/models/models.py:1147-1201``; corresponding service code
exists at ``backend/app/modules/briefings/`` and route surface at
``backend/app/api/routes/briefings.py``. Zero migration creates them →
SQLite-backed unit tests pass via ``Base.metadata.create_all()``, but
any Postgres-backed run crashes on the first ORM query.

Affected tables (FK-dependency order — also creation order):
  1. ``briefing_templates`` — root catalog, no intra-cohort FK.
  2. ``briefing_journals`` — no intra-cohort FK; site/department FKs (SET NULL).
  3. ``briefing_entries`` — FK to briefing_journals (CASCADE) and
     briefing_templates (SET NULL); plus person/site/department/workplace
     FKs (all SET NULL).
  4. ``briefing_signatures`` — FK to briefing_entries (CASCADE) and
     person (SET NULL). No SoftDeleteMixin (signatures are immutable
     compliance evidence — can't be soft-deleted, only the parent entry
     can, and that CASCADEs).

Semantics rationale for ``ondelete`` choices (each mirrors the ORM
``ForeignKey(..., ondelete=...)`` on the model side):

- **journal → entry CASCADE**: deleting a journal is a deliberate
  operator action that means "this logbook is gone"; entries within
  cease to make sense.
- **template → entry SET NULL**: deleting a briefing-type template
  must NOT destroy evidence that the briefing happened. The entry
  becomes "templateless" but still proves the event.
- **person → entry/signature SET NULL**: deleting a person must not
  destroy compliance evidence; the entry/signature stays as a record.
- **entry → signature CASCADE**: a signature has no meaning without
  its parent entry; CASCADE here matches relational semantics.
- **site/department/workplace → entry SET NULL**: organizational
  reorgs (department renamed/deleted) shouldn't destroy compliance
  history.

Antipattern guards:
- **A1 (enum double-create):** N/A — all status/type fields are
  ``String(32)`` (free-form per ORM model), no enum types involved.
- **A3 (split-revision enum drop):** N/A — no enums.
- **Alembic head discipline** ([[alembic-heads-lesson]]): ``down_revision``
  points to iter-29 (``20260528_iter29_version_retrofit``), the true
  head at session 78 start. iter-27/28 were app-code only (no migration);
  iter-29 was the most recent migration added.

Cohort rationale (per [[rb002-enum-migration-cohort]]):
- Same root cause: model-without-migration anti-pattern.
- Same discovery: single audit run flagged all 4 as critical.
- Same feature domain: tightly-coupled briefing flow
  (template → journal → entry → signature).
- Strong intra-cohort FK coupling: 3 of 4 tables have FKs to siblings.
  Bundling enforces atomic apply — landing journal without entry would
  leave the audit script still flagging 3 critical tables, half-done.
- Independent runtime surfaces from incident-family / training-family —
  no entanglement with the deferred ``incident`` business-drift design.

Indexes: each table gets the indexes the ORM declares via
``index=True`` on Mapped columns + the tenant_id index inherited from
``TenantBaseModel``. No speculative composite indexes — matches the
``backend/app/models/models.py`` declarations exactly. If hot-path
analysis later shows a missing index, that's a follow-up iter.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_iter30_briefing_cohort"
down_revision: str | Sequence[str] | None = "20260528_iter29_version_retrofit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- briefing_templates -------------------------------------------------
    op.create_table(
        "briefing_templates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("briefing_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("validity_days", sa.Integer(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_briefing_templates_tenant"
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_briefing_templates_code"),
    )
    op.create_index(
        "ix_briefing_templates_tenant_id",
        "briefing_templates",
        ["tenant_id"],
        unique=False,
    )

    # --- briefing_journals --------------------------------------------------
    op.create_table(
        "briefing_journals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("code", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("journal_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_briefing_journals_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["site.id"],
            name="fk_briefing_journals_site",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_briefing_journals_department",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_briefing_journals_code"),
    )
    op.create_index(
        "ix_briefing_journals_tenant_id",
        "briefing_journals",
        ["tenant_id"],
        unique=False,
    )

    # --- briefing_entries ---------------------------------------------------
    op.create_table(
        "briefing_entries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("briefing_journal_id", sa.String(length=36), nullable=False),
        sa.Column("briefing_template_id", sa.String(length=36), nullable=True),
        sa.Column("person_id", sa.String(length=36), nullable=True),
        sa.Column("instructor_user_id", sa.String(length=36), nullable=True),
        sa.Column("site_id", sa.String(length=36), nullable=True),
        sa.Column("department_id", sa.String(length=36), nullable=True),
        sa.Column("workplace_id", sa.String(length=36), nullable=True),
        sa.Column("briefing_type", sa.String(length=32), nullable=False),
        sa.Column("briefing_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_briefing_entries_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["briefing_journal_id"],
            ["briefing_journals.id"],
            name="fk_briefing_entries_journal",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["briefing_template_id"],
            ["briefing_templates.id"],
            name="fk_briefing_entries_template",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["person_id"],
            ["person.id"],
            name="fk_briefing_entries_person",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["site_id"],
            ["site.id"],
            name="fk_briefing_entries_site",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["department_id"],
            ["department.id"],
            name="fk_briefing_entries_department",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workplace_id"],
            ["workplace.id"],
            name="fk_briefing_entries_workplace",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_briefing_entries_tenant_id",
        "briefing_entries",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_briefing_entries_briefing_journal_id",
        "briefing_entries",
        ["briefing_journal_id"],
        unique=False,
    )
    op.create_index(
        "ix_briefing_entries_person_id",
        "briefing_entries",
        ["person_id"],
        unique=False,
    )

    # --- briefing_signatures ------------------------------------------------
    # Note: no SoftDeleteMixin — signatures are immutable compliance evidence
    # and can only be removed transitively when the parent entry is deleted
    # via CASCADE.
    op.create_table(
        "briefing_signatures",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("briefing_entry_id", sa.String(length=36), nullable=False),
        sa.Column("signer_type", sa.String(length=16), nullable=False),
        sa.Column("signer_user_id", sa.String(length=36), nullable=True),
        sa.Column("signer_person_id", sa.String(length=36), nullable=True),
        sa.Column(
            "signature_mode",
            sa.String(length=32),
            nullable=False,
            server_default="internal_simple",
        ),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signature_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_briefing_signatures_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["briefing_entry_id"],
            ["briefing_entries.id"],
            name="fk_briefing_signatures_entry",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["signer_person_id"],
            ["person.id"],
            name="fk_briefing_signatures_signer_person",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_briefing_signatures_tenant_id",
        "briefing_signatures",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_briefing_signatures_briefing_entry_id",
        "briefing_signatures",
        ["briefing_entry_id"],
        unique=False,
    )


def downgrade() -> None:
    # Reverse FK-dependency order: signature → entry → journal → template.
    op.drop_index(
        "ix_briefing_signatures_briefing_entry_id",
        table_name="briefing_signatures",
    )
    op.drop_index(
        "ix_briefing_signatures_tenant_id", table_name="briefing_signatures"
    )
    op.drop_table("briefing_signatures")

    op.drop_index("ix_briefing_entries_person_id", table_name="briefing_entries")
    op.drop_index(
        "ix_briefing_entries_briefing_journal_id", table_name="briefing_entries"
    )
    op.drop_index("ix_briefing_entries_tenant_id", table_name="briefing_entries")
    op.drop_table("briefing_entries")

    op.drop_index("ix_briefing_journals_tenant_id", table_name="briefing_journals")
    op.drop_table("briefing_journals")

    op.drop_index(
        "ix_briefing_templates_tenant_id", table_name="briefing_templates"
    )
    op.drop_table("briefing_templates")
