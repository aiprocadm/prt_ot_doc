"""iter-24: add journal and ppeitem tables missing from migrations.

Revision ID: 20260527_iter24_journal_ppeitem
Revises: 20260527_iter23_refresh_session_securityauditlog
Create Date: 2026-05-27

Cohort fix for two ``critical`` ORM↔migration drifts surfaced by
``scripts/audit/check_orm_migration_drift.py`` (see Session 71 handoff:
``--summary`` reported 9 critical tables; this PR closes 2 of them).

Root cause:
  - ``Journal`` (``backend/app/models/models.py:2196``) → ``journal`` table,
    domain entity for safety briefing journals (вводный/первичный/повторный
    инструктаж и т.п.). Already referenced by ``journal_entry.journal_id``
    in the model (forward-only FK; the migration that creates ``journalentry``
    in ``6b6dee7c951f_initial_schema.py`` does NOT yet add this FK — that
    is a separate business-drift item, not in this PR's scope).
  - ``PPEItem`` (``backend/app/models/models.py:1318``) → ``ppeitem`` table,
    nomenclature catalog for personal protective equipment. ``PPEIssue``
    (``ppeissue`` in initial_schema) references ``ppeitem.id`` in the model
    but not in its migration — again a separate business-drift item.

Both tables exist in ``ALEMBIC_METADATA.tables`` (the ORM-side schema used
by Alembic autogenerate) but no migration creates them. Tests pass because
``Base.metadata.create_all()`` runs from the model side; production Postgres
crashes on first ORM query (``select(Journal)`` or ``select(PPEItem)``).

Companion enum types (NEW — verified absent from migration tree before
this PR via grep):
  - ``journaltype``: introductory/primary/repeated/target/fire_safety/unscheduled
    (values are the lowercase ``str, enum.Enum`` value strings from
    ``models.py:JournalType``).
  - ``ppeitemcategory``: head/hands/respiratory/body/footwear/fall_protection/other
    (values from ``models.py:PPEItemCategory``).

Antipattern guards:
  - A1 (enum double-create): both enum names are fresh — no other migration
    declares them. Safe to let SQLAlchemy ``sa.Enum(..., name=X)`` auto-create.
  - A3 (drop-recreate enum on dependent column): no drop-recreate pattern
    here; both enums are new + bound to columns in the same migration.

Cohort rationale (per [[rb002-enum-migration-cohort]]):
  - Same root cause (model-without-migration anti-pattern).
  - Same discovery (one audit script run).
  - Independent runtime surfaces: journal endpoints crash separately from
    PPE catalog endpoints; bundling just avoids two onion-peel iterations.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_iter24_journal_ppeitem"
down_revision: str | Sequence[str] | None = (
    "20260527_iter23_refresh_session_securityauditlog"
)
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


JOURNAL_TYPE_VALUES = (
    "introductory",
    "primary",
    "repeated",
    "target",
    "fire_safety",
    "unscheduled",
)

PPE_ITEM_CATEGORY_VALUES = (
    "head",
    "hands",
    "respiratory",
    "body",
    "footwear",
    "fall_protection",
    "other",
)


def upgrade() -> None:
    # --- journal ------------------------------------------------------------
    op.create_table(
        "journal",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column(
            "journal_type",
            sa.Enum(*JOURNAL_TYPE_VALUES, name="journaltype"),
            nullable=False,
        ),
        sa.Column("started_at", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.Date(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_journal_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["company_id"],
            ["company.id"],
            name="fk_journal_company",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_journal_tenant_id", "journal", ["tenant_id"], unique=False)
    op.create_index("ix_journal_company_id", "journal", ["company_id"], unique=False)
    op.create_index(
        "ix_journal_company", "journal", ["tenant_id", "company_id"], unique=False
    )

    # --- ppeitem ------------------------------------------------------------
    op.create_table(
        "ppeitem",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=True),
        sa.Column(
            "category",
            sa.Enum(*PPE_ITEM_CATEGORY_VALUES, name="ppeitemcategory"),
            nullable=False,
        ),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column("default_wear_days", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenant.id"], name="fk_ppeitem_tenant"
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_ppe_item_name"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_ppe_item_code"),
    )
    op.create_index("ix_ppeitem_tenant_id", "ppeitem", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_ppeitem_tenant_id", table_name="ppeitem")
    op.drop_table("ppeitem")

    op.drop_index("ix_journal_company", table_name="journal")
    op.drop_index("ix_journal_company_id", table_name="journal")
    op.drop_index("ix_journal_tenant_id", table_name="journal")
    op.drop_table("journal")

    # Drop enum types last (Postgres-only — SQLite auto-cleans inline CHECK constraints).
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="ppeitemcategory").drop(bind, checkfirst=True)
        sa.Enum(name="journaltype").drop(bind, checkfirst=True)
