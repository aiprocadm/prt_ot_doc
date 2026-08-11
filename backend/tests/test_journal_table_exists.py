"""Pin tests for ``Journal`` (``journal`` table) schema parity.

iter-24 RB-002m (NEW release-blocker class — same anti-pattern as iter-23
RefreshSession/SecurityAuditLog). Discovered by
``scripts/audit/check_orm_migration_drift.py`` (Session 71 ``--summary``
classified it as ``critical``).

Migration ``20260527_iter24_journal_ppeitem`` creates the table with FK to
``company`` (ondelete SET NULL), the ``journaltype`` PG enum, and three
indexes. This file pins the model-side contract so future regressions —
dropping the company FK ondelete, renaming the enum, removing an index —
trip backend-tests before reaching Postgres.

Note: ``JournalEntry.journal_id`` declares ``ForeignKey("journal.id")`` in the
model but the legacy ``6b6dee7c951f_initial_schema.py`` migration that creates
``journalentry`` does NOT yet add this FK column. That is a separate
business-drift fix (would also require flipping ``journalentry.entry_type``
from ``String(128)`` to the new ``journaltype`` enum). Out of iter-24 scope.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import Journal, JournalType


def test_journal_has_required_columns() -> None:
    columns = inspect(Journal).columns
    required = {
        "id",
        "tenant_id",
        "company_id",
        "title",
        "journal_type",
        "started_at",
        "closed_at",
        "metadata_json",
        "deleted_at",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(
        columns.keys()
    ), f"journal missing columns: {required - set(columns.keys())}"


def test_journal_company_fk_sets_null_on_company_delete() -> None:
    column = inspect(Journal).columns["company_id"]
    foreign_keys = list(column.foreign_keys)

    assert len(foreign_keys) == 1, "company_id must have exactly one FK"
    fk = foreign_keys[0]
    assert fk.column.table.name == "company"
    assert fk.column.name == "id"
    assert fk.ondelete == "SET NULL", (
        "ondelete must be SET NULL — deleting a company should preserve "
        "the journal record (regulatory/historical audit), only detach the link"
    )


def test_journal_type_uses_journaltype_enum() -> None:
    column = inspect(Journal).columns["journal_type"]
    # SQLAlchemy stores the enum class on column.type for sa.Enum(PyEnum).
    assert column.type.enum_class is JournalType, (
        "journal.journal_type must be Enum(JournalType) — string column would "
        "lose type-safety and diverge from JournalEntry's intended migration"
    )
    expected_values = {
        "introductory",
        "primary",
        "repeated",
        "target",
        "fire_safety",
        "unscheduled",
    }
    actual_values = {member.value for member in JournalType}
    assert expected_values == actual_values, (
        f"JournalType value drift: {expected_values ^ actual_values}. "
        "If you add a value, also extend the PG enum via ALTER TYPE in a "
        "separate revision (see [[rb002-enum-migration-cohort]] iter-19)."
    )


def test_journal_indexes_for_tenant_company_lookups() -> None:
    index_names = {idx.name for idx in Journal.__table__.indexes}
    assert "ix_journal_company" in index_names, (
        "ix_journal_company on (tenant_id, company_id) is required for "
        "tenant-scoped company-filtered listing — without it large tenants "
        "trigger seq-scan on /api/v1/journals?company_id=..."
    )


def test_iter24_migration_chains_to_iter23_head() -> None:
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter24_journal_ppeitem.py"
    )
    assert migration_path.exists(), f"iter-24 migration file missing at {migration_path}"

    spec = importlib.util.spec_from_file_location("iter24_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "20260527_iter24_journal_ppeitem"
    # iter-24 must chain to iter-23 (current head) — chaining to an older
    # revision would create a parallel branch and break `alembic upgrade head`
    # with "Multiple head revisions" (the lesson from iter-21 PR #589 first
    # attempt — see [[alembic-heads-lesson]]).
    assert module.down_revision == "20260527_iter23_refresh_session_securityauditlog"


def test_iter24_migration_creates_both_journal_and_ppeitem() -> None:
    # Guard against accidental scope-creep or scope-loss: this migration must
    # create exactly the two cohort tables it announces in its docstring.
    from pathlib import Path  # noqa: PLC0415

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter24_journal_ppeitem.py"
    )
    src = migration_path.read_text(encoding="utf-8")
    assert 'op.create_table(\n        "journal"' in src, "iter-24 must create the journal table"
    assert (
        'op.create_table(\n        "ppeitem"' in src
    ), "iter-24 must create the ppeitem table (cohort partner)"
