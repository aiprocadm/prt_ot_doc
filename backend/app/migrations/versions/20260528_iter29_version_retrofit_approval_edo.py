"""iter-29: retrofit ``version`` column on 8 approval / signature / EDO tables.

Revision ID: 20260528_iter29_version_retrofit
Revises: 20260527_iter26_inspection_result
Create Date: 2026-05-28

Bug class: ORM-Migration drift, flavor (b) — naming-mismatch / missing-column.
``TenantBaseModel`` (``backend/app/models/base.py:51``) inherits
``VersionedMixin``, which not only declares ``version: Mapped[int]`` but also
sets ``__mapper_args__["version_id_col"] = cls.version``. That activates
SQLAlchemy's optimistic concurrency control: every UPDATE appends
``WHERE version = <old> RETURNING version`` and bumps the column. If the
column doesn't exist in DDL, the UPDATE fails immediately on Postgres with
``UndefinedColumnError``, blocking every write through the ORM. SQLite is
tolerant (column absent → SA falls back to plain UPDATE) which is why
unit tests pass while perf-smoke / restore-drill on Postgres crash.

Affected tables (audit'd via ``scripts/audit/version_column_drift.py`` —
all inherit ``TenantBaseModel`` but their creator migration omitted the
``version`` column):

    20260303_next30_approval_signing_core.py:
      - approval_processes
      - approval_tasks
      - approval_decision_logs
      - signature_requests
      - edo_envelopes

    20260330_next57_approval_sign_edo_orchestration.py:
      - approval_instance_steps
      - edo_status_events
      - edo_webhook_inbox

The same author who wrote the next30 + next57 migrations did add ``version``
correctly on ``approval_route_steps`` and ``approval_instances`` (both in
next57), confirming awareness of the mixin — these 8 are simple omissions,
not intentional opt-outs.

Fix: ``op.add_column(<t>, sa.Column("version", sa.Integer(), nullable=False,
server_default="1"))`` × 8. ``server_default="1"`` backfills existing rows
atomically with the ALTER (PG semantics) and stays in place permanently to
match the convention used by ``approval_route_steps`` / ``approval_instances``
in the same source migration.

No FKs, indexes, or enum types involved — pure mixin column retrofit.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260528_iter29_version_retrofit"
down_revision: str | Sequence[str] | None = "20260527_iter26_inspection_result"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Stable alphabetical order so a future drift diff against this file is
# easy to read. ORM model class noted in comment for each row.
_TABLES: tuple[str, ...] = (
    "approval_decision_logs",     # ApprovalDecisionLog
    "approval_instance_steps",    # ApprovalInstanceStep
    "approval_processes",         # ApprovalProcess
    "approval_tasks",             # ApprovalTask
    "edo_envelopes",              # EdoEnvelope
    "edo_status_events",          # EdoStatusEvent
    "edo_webhook_inbox",          # EdoWebhookInbox
    "signature_requests",         # SignatureRequest
)


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "version",
                sa.Integer(),
                nullable=False,
                server_default="1",
            ),
        )


def downgrade() -> None:
    # Reverse order so any downstream tooling that snapshots schema
    # observes inverse symmetry with upgrade().
    for table in reversed(_TABLES):
        op.drop_column(table, "version")
