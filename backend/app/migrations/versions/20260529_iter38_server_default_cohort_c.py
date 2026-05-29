"""iter-38: retrofit ``server_default`` for the Subset C parity cohort.

Revision ID: 20260529_iter38_server_default_c
Revises: 20260529_iter37_server_default_ab
Create Date: 2026-05-29

Closes the entire remaining server_default parity drift surfaced by
``scripts/audit/server_default_parity.py``: 33 columns across 29
tables, all enum-typed (Subset C from Session 83's audit).

After iter-37 dispatched Subsets A (int/bool) and B (string) — 19 cols
across 15 tables — Subset C was the last open category. This iter ships
it as a single mechanical cohort: each row is one ``op.alter_column``,
adding ``server_default=<UPPER_CASE_NAME>`` for SA Enum-class columns
and ``server_default="customer"`` for the lone positional-string Enum
(``tenant.kind``). The audit's drift count goes 33 → 0.

Storage semantics:
  * For columns declared ``mapped_column(Enum(MyEnumClass[, name=...]))``
    on PG with the default ``native_enum=True``, SQLAlchemy stores the
    enum **member name** (UPPER_CASE attribute) — not the value. So
    ``default=IncidentSeverity.MEDIUM`` lands as ``'MEDIUM'`` in DB, and
    the corresponding ``server_default`` must be the same UPPER_CASE
    string.
  * For ``tenant.kind`` — declared as
    ``Enum("customer", "branch", "contractor", name="tenantkind")`` with
    literal positional values + ``default="customer"`` — the stored
    value IS the lowercase literal. ``server_default="customer"``.

Why plain string instead of ``sa.text("'<value>'::<enum_name>")``:
  * Repo precedent at ``20260319_next48_billing_core.py:97`` —
    ``sa.Column("status", invoice_status, nullable=False,
    server_default="draft")`` — uses plain string for a PG enum column.
  * For ``ALTER TABLE ... ALTER COLUMN ... SET DEFAULT 'val'`` on a PG
    column whose type is already the named enum, PG performs implicit
    text-to-enum cast (assignment context is unambiguous). Same logic
    applies as ``Column(enum_type, server_default='val')`` in
    ``create_table`` — see billing_core.
  * Plain string is dialect-portable: SQLite stores SA Enum as VARCHAR
    + optional CHECK constraint, so plain string is the natural form.
    ``sa.text("'val'::enum_name")`` would be PG-only syntax (``::``
    cast).
  * The audit (``server_default_parity.py:_alter_column_target``) only
    requires ``server_default=`` kwarg to be present + not ``None``;
    the literal form is irrelevant for parity bookkeeping.

About ``existing_type=sa.String(length=64)`` placeholder:
  * Alembic uses ``existing_type`` only for autogenerate diff and for
    SQLite batch-mode reconstruction. This migration uses
    ``op.alter_column`` directly (no batch), changes only
    ``server_default`` (no type change), so ``existing_type`` is
    informational.
  * On SQLite the columns ARE effectively VARCHAR (SA Enum without
    native_enum falls back to VARCHAR + CHECK), so ``String(64)`` is
    structurally accurate from SQLite's perspective.
  * Mirrors iter-37's existing_type pattern (Integer / Boolean /
    String) — keeps cohort tests uniform.

Operational impact: any raw-SQL path that inserts without explicitly
specifying these enum columns (perf-baseline ``COPY``, restore-drill
SQL dumps, manual ops fixes, alembic ``op.execute("INSERT ...")``) now
gets the default applied at DB level, matching the ORM's ``default=``
behavior.

Each upgrade ``alter_column`` is paired with a downgrade that resets
``server_default=None`` — same shape as iter-37.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_iter38_server_default_c"
down_revision: str | Sequence[str] | None = "20260529_iter37_server_default_ab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # Subset C — 32 SA-Enum cohort columns + 1 positional-Enum tenant.kind #
    # Sorted alphabetically by (table, column) for stable diff.            #
    # ------------------------------------------------------------------ #
    op.alter_column(
        "approval_instance_steps",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="PENDING",
    )
    op.alter_column(
        "approval_instances",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="DRAFT",
    )
    op.alter_column(
        "approval_processes",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="PENDING",
    )
    op.alter_column(
        "approval_route_steps",
        "step_type",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="APPROVE",
    )
    op.alter_column(
        "approval_tasks",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="OPEN",
    )
    op.alter_column(
        "attestation",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="ACTIVE",
    )
    op.alter_column(
        "client_request_tickets",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="OPEN",
    )
    op.alter_column(
        "edo_envelopes",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="QUEUED",
    )
    op.alter_column(
        "equipment",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="ACTIVE",
    )
    op.alter_column(
        "idempotency_keys",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="PENDING",
    )
    op.alter_column(
        "incident",
        "severity",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="MEDIUM",
    )
    op.alter_column(
        "incident",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="REPORTED",
    )
    op.alter_column(
        "inspection_prescription",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="OPEN",
    )
    op.alter_column(
        "npa",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="ACTIVE",
    )
    op.alter_column(
        "pack_run_items",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="QUEUED",
    )
    op.alter_column(
        "pack_runs",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="QUEUED",
    )
    op.alter_column(
        "package_preset_items",
        "output_format",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="BOTH",
    )
    op.alter_column(
        "package_preset_items",
        "replace_mode",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="NONE",
    )
    op.alter_column(
        "package_presets_v2",
        "source_type",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="CSV",
    )
    op.alter_column(
        "package_presets_v2",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="DRAFT",
    )
    op.alter_column(
        "package_profiles_v2",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="DRAFT",
    )
    op.alter_column(
        "package_requirements",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="MISSING",
    )
    op.alter_column(
        "package_requirements",
        "type",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="FILE",
    )
    op.alter_column(
        "package_runs",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="DRAFT",
    )
    op.alter_column(
        "permit",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="ACTIVE",
    )
    op.alter_column(
        "pipeline_runs",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="QUEUED",
    )
    op.alter_column(
        "plantask",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="OPEN",
    )
    op.alter_column(
        "ppeissue",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="ISSUED",
    )
    op.alter_column(
        "ppeitem",
        "category",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="OTHER",
    )
    op.alter_column(
        "template",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="DRAFT",
    )
    op.alter_column(
        "templateversion",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="UPLOADED",
    )
    # tenant.kind: positional-Enum form, default is literal lowercase
    # "customer" — not an enum member name. Stored as-is in PG enum.
    op.alter_column(
        "tenant",
        "kind",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="customer",
    )
    op.alter_column(
        "training_session",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default="SCHEDULED",
    )


def downgrade() -> None:
    # Reverse alphabetical order — inverse symmetry of upgrade.
    op.alter_column(
        "training_session",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "tenant",
        "kind",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "templateversion",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "template",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "ppeitem",
        "category",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "ppeissue",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "plantask",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "pipeline_runs",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "permit",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_runs",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_requirements",
        "type",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_requirements",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_profiles_v2",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_presets_v2",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_presets_v2",
        "source_type",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_preset_items",
        "replace_mode",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "package_preset_items",
        "output_format",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "pack_runs",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "pack_run_items",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "npa",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "inspection_prescription",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "incident",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "incident",
        "severity",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "idempotency_keys",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "equipment",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "edo_envelopes",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "client_request_tickets",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "attestation",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "approval_tasks",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "approval_route_steps",
        "step_type",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "approval_processes",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "approval_instances",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
    op.alter_column(
        "approval_instance_steps",
        "status",
        existing_type=sa.String(length=64),
        existing_nullable=False,
        server_default=None,
    )
