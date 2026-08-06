"""Pin tests for ``User.company_id`` column + FK + index schema parity.

iter-21 RB-002i (new release-blocker class — ORM ↔ migration drift, distinct
from the RB-002a..h enum-values cohort closed by iter-17..19). ``User.company_id``
was added to ``backend/app/models/models.py`` (commit ``0d4d140`` "Harden
refresh token handling with cookie rotation and revocation") without a
paired Alembic migration. ``6b6dee7c951f_initial_schema.py:365-380`` creates
``user`` without the column and no subsequent migration adds it.

SQLite-backed unit tests pass because ``Base.metadata.create_all()`` builds
schema directly from the model, so the column appears in the SQLite test DB.
PG-backed perf-smoke fails at api-1 startup (``dev_bootstrap.bootstrap_admin_user``)
with ``asyncpg.exceptions.UndefinedColumnError: column user.company_id
does not exist`` when SQLAlchemy issues the eager-loaded
``SELECT ... FROM user LEFT JOIN company ON company.id = user.company_id``.
The ``alembic-postgres-upgrade`` CI job didn't catch it — that job only
runs migrations, never ORM queries.

iter-21 ships migration ``20260527_iter21_user_company_id`` that adds the
column, the ``fk_user_company`` foreign key (ondelete SET NULL), and the
``ix_user_company`` composite index. This file pins the model-side contract
the migration must satisfy, so future drift (model removes the column /
the FK loses ondelete=SET NULL / the index disappears) is caught at
backend-tests CI before another regression slips into perf-smoke.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import User


def test_user_has_company_id_column_with_correct_type() -> None:
    column = inspect(User).columns["company_id"]

    assert column.nullable is True, "User.company_id must be nullable (matches migration)"
    assert column.type.length == 36, "User.company_id must be String(36) (matches FK to company.id)"


def test_user_company_id_foreign_key_targets_company_with_set_null() -> None:
    column = inspect(User).columns["company_id"]
    foreign_keys = list(column.foreign_keys)

    assert len(foreign_keys) == 1, "User.company_id must have exactly one FK"
    fk = foreign_keys[0]
    assert fk.column.table.name == "company"
    assert fk.column.name == "id"
    assert fk.ondelete == "SET NULL", (
        "ondelete must be SET NULL — matches migration fk_user_company "
        "and avoids cascade-deleting users on company removal"
    )


def test_user_table_has_company_index_for_tenant_scoped_lookups() -> None:
    index_names = {idx.name for idx in User.__table__.indexes}
    assert "ix_user_company" in index_names, (
        "ix_user_company composite index must be present "
        "(matches migration 20260527_iter21_user_company_id)"
    )

    company_index = next(idx for idx in User.__table__.indexes if idx.name == "ix_user_company")
    assert [col.name for col in company_index.columns] == [
        "tenant_id",
        "company_id",
    ], "ix_user_company must be on (tenant_id, company_id) for tenant-scoped lookups"


def test_iter21_migration_chains_to_current_head() -> None:
    # Guard against rebase mishap dropping the migration file or its
    # down_revision link to the prior head. Migration module names start
    # with a digit, so they can't be `import`ed by statement — load via
    # importlib instead (same trick alembic itself uses internally).
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter21_user_company_id.py"
    )
    assert migration_path.exists(), f"iter-21 migration file missing at {migration_path}"

    spec = importlib.util.spec_from_file_location("iter21_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "20260527_iter21_user_company_id"
    # Chain to true alembic head as of 2026-05-27. Picking the wrong
    # head produces the "Multiple head revisions" error on
    # alembic-postgres-upgrade CI (see iter-21 PR #589 first attempt).
    assert module.down_revision == "20260517_saved_calendar_views"
