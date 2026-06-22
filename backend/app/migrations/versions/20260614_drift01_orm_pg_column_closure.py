"""drift01: close ORM<->PG add_column drift from the #643-#653 feature train.

Revision ID: 20260614_drift01_orm_pg_column_closure
Revises: 20260613_ed04_briefing_require_signature_code
Create Date: 2026-06-14

Bug class: ORM-Migration drift, flavor (a) — absent-column. While CI was off,
a train of features (#643-#653: incidents, medical, contractors, ppe, edo)
added/changed ORM models. Several columns were only ever materialised via the
SQLite ``create_all`` path and never got an Alembic migration, so they are
ABSENT on a real Postgres schema after ``alembic upgrade head``. The app then
SELECTs them at startup and crashes, e.g. the perf-smoke job:

    asyncpg.exceptions.UndefinedColumnError: column ppeissue.deleted_at
        does not exist

This migration was produced by diffing the app's ORM metadata against a live
PG schema with ``alembic.autogenerate.compare_metadata`` after ``upgrade head``.
It adds EVERY ``add_column`` the diff reported (15 columns across 14 tables);
no ``add_table`` items were found (the contractors-domain core tables are
created by the amended con01 migration). Pure additive closure — non-breaking
diff noise (extra DB tables, type/default/index variations, native-enum
reflection quirks) is deliberately ignored.

Three column families, each matched to its ORM declaration:

1. ``version`` (Integer NOT NULL server_default="1") on 11 tables that inherit
   ``TenantBaseModel`` -> ``VersionedMixin`` (backend/app/models/base.py). The
   mixin also sets ``version_id_col``, so every ORM UPDATE references the
   column; without it Postgres raises UndefinedColumnError on every write.
   ``server_default="1"`` backfills existing rows atomically with the ALTER and
   matches the convention established by iter-29 / iter-46 / iter-48.

2. ``deleted_at`` (DateTime(timezone=True) NULL) on ``incident`` and
   ``ppeissue`` — both ORM classes mix in ``SoftDeleteMixin``
   (``deleted_at: Mapped[datetime | None]``); soft-delete queries filter
   ``WHERE deleted_at IS NULL``.

3. ``risk_assessments.position_id`` / ``risk_assessments.document_pack_id``
   (String(36) NULL, indexed FK) — declared on ``RiskAssessment``
   (backend/app/models/risk.py) as nullable ForeignKey columns.

Idempotent / retry-safe: env.py runs migrations under AUTOCOMMIT (a failed
multi-statement migration is not rolled back), so every step is guarded by an
inspector existence check, mirroring iter-42. Works on both PG and SQLite.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260614_drift01_orm_pg_column_closure"
down_revision: str | Sequence[str] | None = "20260613_ed04_briefing_require_signature_code"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Tables inheriting VersionedMixin whose creator migration omitted ``version``.
# Alphabetical for a readable future drift diff.
_VERSION_TABLES: tuple[str, ...] = (
    "approval_decisions",  # ApprovalDecision
    "approval_requests",  # ApprovalRequest
    "document_artifacts",  # DocumentArtifact
    "document_job_steps",  # DocumentJobStep
    "document_jobs",  # DocumentJob
    "edo_messages",  # EdoMessage
    "edo_receipts",  # EdoReceipt
    "edo_status_history",  # EdoStatusHistory
    "notification_templates",  # NotificationTemplate
    "outbox_events",  # OutboxEvent
    "pdf_conversion_runs",  # PdfConversionRun
)

# SoftDeleteMixin tables missing ``deleted_at``.
_DELETED_AT_TABLES: tuple[str, ...] = (
    "incident",  # Incident
    "ppeissue",  # PPEIssue
)


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if table not in insp.get_table_names():
        return False
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()

    # 1. version (Integer NOT NULL, server_default "1").
    for table in _VERSION_TABLES:
        if not _has_column(bind, table, "version"):
            op.add_column(
                table,
                sa.Column(
                    "version",
                    sa.Integer(),
                    nullable=False,
                    server_default="1",
                ),
            )

    # 2. deleted_at (DateTime tz NULL) — soft delete.
    for table in _DELETED_AT_TABLES:
        if not _has_column(bind, table, "deleted_at"):
            op.add_column(
                table,
                sa.Column(
                    "deleted_at",
                    sa.DateTime(timezone=True),
                    nullable=True,
                ),
            )

    # 3. risk_assessments nullable indexed FK columns.
    if not _has_column(bind, "risk_assessments", "position_id"):
        op.add_column(
            "risk_assessments",
            sa.Column(
                "position_id",
                sa.String(length=36),
                sa.ForeignKey("position.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_risk_assessments_position_id",
            "risk_assessments",
            ["position_id"],
        )
    if not _has_column(bind, "risk_assessments", "document_pack_id"):
        op.add_column(
            "risk_assessments",
            sa.Column(
                "document_pack_id",
                sa.String(length=36),
                sa.ForeignKey("document_pack.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_risk_assessments_document_pack_id",
            "risk_assessments",
            ["document_pack_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()

    if _has_column(bind, "risk_assessments", "document_pack_id"):
        op.drop_index(
            "ix_risk_assessments_document_pack_id",
            table_name="risk_assessments",
        )
        op.drop_column("risk_assessments", "document_pack_id")
    if _has_column(bind, "risk_assessments", "position_id"):
        op.drop_index(
            "ix_risk_assessments_position_id",
            table_name="risk_assessments",
        )
        op.drop_column("risk_assessments", "position_id")

    for table in reversed(_DELETED_AT_TABLES):
        if _has_column(bind, table, "deleted_at"):
            op.drop_column(table, "deleted_at")

    for table in reversed(_VERSION_TABLES):
        if _has_column(bind, table, "version"):
            op.drop_column(table, "version")
