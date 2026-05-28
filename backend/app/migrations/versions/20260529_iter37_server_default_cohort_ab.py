"""iter-37: retrofit ``server_default`` for the Subset A+B parity cohort.

Revision ID: 20260529_iter37_server_default_ab
Revises: 20260528_iter32_business_drift
Create Date: 2026-05-29

Bug class: server_default parity drift — column declared on the model as
``nullable=False, default=<literal>`` but the matching migration left
the DB-side column without a ``server_default``. Same family as iter-32
(which fixed exactly one instance: ``ppeissue.quantity``), now scaled to
the cohort surfaced by ``scripts/audit/server_default_parity.py``
(iter-36, Session 83).

Closes the safe-to-ship subset where every column maps to a primitive
type (Integer, Boolean, String) and a clean ``server_default`` form:

  * **Subset A** — int/bool literals (15 cols across 12 tables)
  * **Subset B** — short string literals (4 cols across 4 tables)

Deferred to a follow-up iter (needs PG enum cast / SQLite dialect
review):

  * **Subset C** — enum-typed defaults (32 cols), plus ``tenant.kind``
    which has a literal string default but ``Enum(name="tenantkind")``
    column type. Translating to ``server_default`` requires
    ``sa.text("'<value>'::tenantkind")`` on PG and a verified SQLite
    fallback — out of scope here.

Operational impact: any raw-SQL path that inserts without explicitly
specifying these columns (perf-baseline ``COPY``, restore-drill dumps,
manual ops fixes) currently hits ``NOT NULL`` violation on Postgres.
Python's ``default=`` only fires on ORM inserts.

Each ``alter_column`` is paired with a downgrade that resets
``server_default=None`` — same shape as the canonical 2025-02-18 / 03-25
patterns already established in this repo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter37_server_default_ab"
down_revision: str | Sequence[str] | None = "20260528_iter32_business_drift"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Subset A.int — 7 Integer columns                                    #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "document_pack_item",
        "order",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="0",
    )
    op.alter_column(
        "pack_runs",
        "selected_rows_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="0",
    )
    op.alter_column(
        "pack_runs",
        "source_rows_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="0",
    )
    op.alter_column(
        "ppeitem",
        "default_wear_days",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="365",
    )
    op.alter_column(
        "ppenorm",
        "interval_days",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="365",
    )
    op.alter_column(
        "ppenorm",
        "quantity",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="1",
    )
    op.alter_column(
        "warehouseppe",
        "quantity",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default="0",
    )

    # ------------------------------------------------------------------ #
    # Subset A.bool — 8 Boolean columns                                   #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "api_key",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "document_pack",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "document_pack_item",
        "required",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "package_preset_items",
        "is_required",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "tenant",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "training_plan",
        "is_mandatory",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "user",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )
    op.alter_column(
        "webhook_subscription",
        "enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=sa.true(),
    )

    # ------------------------------------------------------------------ #
    # Subset B — 4 String columns                                         #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "api_key",
        "scopes",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        server_default="api:read",
    )
    op.alter_column(
        "auditlog",
        "ip",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="unknown",
    )
    op.alter_column(
        "edo_webhook_inbox",
        "status",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        server_default="received",
    )
    op.alter_column(
        "securityauditlog",
        "ip",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="unknown",
    )


def downgrade() -> None:
    # Reverse order so downstream tooling observes inverse symmetry.

    # Subset B reverse --------------------------------------------------- #
    op.alter_column(
        "securityauditlog",
        "ip",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "edo_webhook_inbox",
        "status",
        existing_type=sa.String(length=16),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "auditlog",
        "ip",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "api_key",
        "scopes",
        existing_type=sa.String(length=255),
        existing_nullable=False,
        server_default=None,
    )

    # Subset A.bool reverse --------------------------------------------- #
    op.alter_column(
        "webhook_subscription",
        "enabled",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "user",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "training_plan",
        "is_mandatory",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "tenant",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_preset_items",
        "is_required",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "document_pack_item",
        "required",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "document_pack",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "api_key",
        "is_active",
        existing_type=sa.Boolean(),
        existing_nullable=False,
        server_default=None,
    )

    # Subset A.int reverse ---------------------------------------------- #
    op.alter_column(
        "warehouseppe",
        "quantity",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "ppenorm",
        "quantity",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "ppenorm",
        "interval_days",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "ppeitem",
        "default_wear_days",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "pack_runs",
        "source_rows_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "pack_runs",
        "selected_rows_count",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "document_pack_item",
        "order",
        existing_type=sa.Integer(),
        existing_nullable=False,
        server_default=None,
    )
