"""iter-41: journalentry concept resolution — replace generic event-log shape
with safety-briefing entry shape that matches the current
``app.models.models.JournalEntry`` declaration.

Closes 1 of the 5 column_drift_lite business-drift tables (Session 85
baseline). This is the "concept drift" entry from `[[mvp-release-blockers]]`
drift-class backlog — the model was evolved post-initial-schema into a
domain-specific safety-briefing entry, but the migration was never updated.

Original shape (from ``6b6dee7c951f_initial_schema.py:209``):
    entry_type   String(128)  NOT NULL
    payload      JSON         NOT NULL
    occurred_at  DateTime(tz) NOT NULL

Current model shape (``backend/app/models/models.py:2215``):
    journal_id     String(36) NOT NULL  FK → journal.id      (index=True)
    person_id      String(36) NOT NULL  FK → person.id       (index=True)
    entry_type     Enum(JournalType)    NOT NULL
    entry_date     Date         NOT NULL  default=date.today (today)
    instructor     String(255)  NULL
    notes          Text         NULL
    metadata_json  JSON         NOT NULL  default=dict ({})
    + UniqueConstraint(tenant_id, journal_id, person_id, entry_type, entry_date)
    + Index(tenant_id, entry_type)

The two shapes are mutually incompatible (different NOT NULL cols with
no overlap beyond ``entry_type``, and the type of ``entry_type`` itself
changed from String → Enum). The cleanest representation is to drop the
old table and recreate it with the model shape — this is what this
migration does.

Data-loss caveat: the old ``payload`` + ``occurred_at`` values are lost.
This is acceptable because:
- The model has been deployed with a mismatched schema; ORM writes via
  ``JournalEntry(...)`` would have failed with ``UndefinedColumnError``
  on PostgreSQL (the modern fields don't exist in the table).
- The endpoints in ``backend/app/api/routes/journals.py`` actively use
  the modern fields. Any production environment that ran these would
  have crashed before any rows landed.
- The model's NOT NULL FKs (``journal_id``, ``person_id``) have no
  backfill source — if the table did contain old-shape rows, there'd
  be no way to satisfy the new constraints anyway.

Companion work: this also activates the API surface in ``journals.py``
that was effectively broken since the model evolved past the initial
schema.

The ``journaltype`` PG enum was first created by iter-24's ``journal``
table migration (``20260527_iter24_journal_ppeitem.py``). We reuse it
via ``create_type=False`` to avoid the "type already exists" error.

After iter-41 lands the column_drift_lite business-drift count drops
from 5 → 4 tables (journalentry cleared; remaining: incident family ×3).

NOTE on alembic heads: this migration chains from
``20260529_iter38_server_default_c`` (the latest revision on ``main`` at
session-start). The parallel branch ``fix/iter-40-training-certificates-legacy-cols``
also chains from the same parent. When BOTH iter-40 and iter-41 land on
``main``, alembic will detect multiple heads and a merge migration must
be added (``alembic merge -m "..." iter-40 iter-41``).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter41_journalentry_concept"
down_revision: str | Sequence[str] | None = "20260529_iter38_server_default_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Mirror of iter-24's JOURNAL_TYPE_VALUES so the enum reference here is
# identical to the source-of-truth definition in
# ``20260527_iter24_journal_ppeitem.py:64``. Kept local — importing across
# migration files is an alembic anti-pattern.
JOURNAL_TYPE_VALUES = (
    "introductory",
    "primary",
    "repeated",
    "target",
    "fire_safety",
    "unscheduled",
)


def upgrade() -> None:
    # Drop the original generic event-log shape created by
    # 6b6dee7c951f_initial_schema.py:209.
    op.drop_index(op.f("ix_journalentry_tenant_id"), table_name="journalentry")
    op.drop_table("journalentry")

    # Recreate with the current model shape. Reuses the existing
    # `journaltype` PG enum (created by iter-24).
    op.create_table(
        "journalentry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("journal_id", sa.String(length=36), nullable=False),
        sa.Column("person_id", sa.String(length=36), nullable=False),
        sa.Column(
            "entry_type",
            sa.Enum(*JOURNAL_TYPE_VALUES, name="journaltype", create_type=False),
            nullable=False,
        ),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("instructor", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["journal_id"], ["journal.id"]),
        sa.ForeignKeyConstraint(["person_id"], ["person.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "journal_id",
            "person_id",
            "entry_type",
            "entry_date",
            name="uq_journal_entry_unique_person_date",
        ),
    )
    op.create_index(
        op.f("ix_journalentry_tenant_id"),
        "journalentry",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_journalentry_journal_id"),
        "journalentry",
        ["journal_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_journalentry_person_id"),
        "journalentry",
        ["person_id"],
        unique=False,
    )
    op.create_index(
        "ix_journal_entry_type",
        "journalentry",
        ["tenant_id", "entry_type"],
        unique=False,
    )


def downgrade() -> None:
    # Drop the new shape (with indexes + uq + FKs all attached to the
    # table, dropping the table cascades them automatically).
    op.drop_index("ix_journal_entry_type", table_name="journalentry")
    op.drop_index(op.f("ix_journalentry_person_id"), table_name="journalentry")
    op.drop_index(op.f("ix_journalentry_journal_id"), table_name="journalentry")
    op.drop_index(op.f("ix_journalentry_tenant_id"), table_name="journalentry")
    op.drop_table("journalentry")

    # Recreate the original initial-schema generic shape so downstream
    # migrations from that era (none current) can apply cleanly.
    op.create_table(
        "journalentry",
        sa.Column("entry_type", sa.String(length=128), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_journalentry_tenant_id"),
        "journalentry",
        ["tenant_id"],
        unique=False,
    )
