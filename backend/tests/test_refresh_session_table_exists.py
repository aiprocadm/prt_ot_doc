"""Pin tests for ``RefreshSession`` (``refresh_session`` table) schema parity.

iter-23 RB-002j (NEW release-blocker class — discovered by
``scripts/audit/check_orm_migration_drift.py``). Same anti-pattern as iter-21
``User.company_id``: ``RefreshSession`` was added to
``backend/app/models/models.py:473`` without a paired Alembic migration. The
model declares a ``refresh_session`` table with FKs to ``tenant`` and ``user``,
but no migration creates it. SQLite tests pass via
``Base.metadata.create_all()``; Postgres production crashes the first time
``auth.py:create_refresh_session()`` issues an INSERT.

iter-23 migration ``20260527_iter23_refresh_session_securityauditlog`` creates
the table with all FKs/indexes/unique constraints. This file pins the
model-side contract so any future drift (e.g. removing the user FK ondelete=
CASCADE, dropping token_jti uniqueness) trips backend-tests before reaching
production.
"""

from __future__ import annotations

from sqlalchemy import inspect

from app.models.models import RefreshSession


def test_refresh_session_has_required_columns() -> None:
    columns = inspect(RefreshSession).columns
    required = {
        "id",
        "tenant_id",
        "user_id",
        "family_id",
        "token_jti",
        "parent_token_jti",
        "replaced_by_token_jti",
        "expires_at",
        "last_seen_at",
        "revoked_at",
        "revoke_reason",
        "created_at",
        "updated_at",
        "version",
    }
    assert required.issubset(
        columns.keys()
    ), f"refresh_session missing columns: {required - set(columns.keys())}"


def test_refresh_session_user_fk_cascades_on_delete() -> None:
    column = inspect(RefreshSession).columns["user_id"]
    foreign_keys = list(column.foreign_keys)

    assert len(foreign_keys) == 1, "user_id must have exactly one FK"
    fk = foreign_keys[0]
    assert fk.column.table.name == "user"
    assert fk.column.name == "id"
    assert fk.ondelete == "CASCADE", (
        "ondelete must be CASCADE — deleting a user should remove their "
        "refresh sessions to prevent zombie token rotation lookups"
    )


def test_refresh_session_token_jti_is_unique_and_indexed() -> None:
    column = inspect(RefreshSession).columns["token_jti"]
    assert (
        column.unique is True
    ), "token_jti must be unique — duplicate jti would defeat rotation revocation"
    index_names = {idx.name for idx in RefreshSession.__table__.indexes}
    assert (
        "ix_refresh_session_token_jti" in index_names
    ), "ix_refresh_session_token_jti index required for fast consume lookups"


def test_refresh_session_composite_indexes_for_family_queries() -> None:
    index_names = {idx.name for idx in RefreshSession.__table__.indexes}
    assert "ix_refresh_session_user_family" in index_names, (
        "Composite (tenant_id, user_id, family_id) index needed for "
        "user-scoped family enumeration on revoke_all"
    )
    assert "ix_refresh_session_family_active" in index_names, (
        "Composite (tenant_id, family_id, revoked_at) index needed for "
        "active-session queries during rotation"
    )


def test_iter23_migration_chains_to_iter21_head() -> None:
    # Same importlib pattern as test_user_company_id_column_exists.py — migration
    # filenames start with a digit, so they can't be `import`-ed directly.
    import importlib.util  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260527_iter23_refresh_session_securityauditlog.py"
    )
    assert migration_path.exists(), f"iter-23 migration file missing at {migration_path}"

    spec = importlib.util.spec_from_file_location("iter23_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "20260527_iter23_refresh_session_securityauditlog"
    # iter-23 must chain to iter-21 (current alembic head); chaining to an
    # older revision would create a parallel branch and break
    # `alembic upgrade head` with "Multiple head revisions". iter-22 was a
    # code-only PR (no migration) so iter-21 remains the head.
    assert module.down_revision == "20260527_iter21_user_company_id"
