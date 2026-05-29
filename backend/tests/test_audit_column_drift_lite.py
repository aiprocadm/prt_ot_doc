"""Tests for ``scripts/audit/column_drift_lite.py``.

Pure AST analysis tests — no app imports, runs on any Python >= 3.10.

Covers:
  - Model-side column extraction (skips ``relationship(...)`` values, keeps
    ``mapped_column(...)`` / ``Column(...)``).
  - Migration-side column collection: direct create_table, helper-wrapped,
    add_column literal, add_column with loop variable (v3 reuse), batch
    add_column, drop_column, alter_column rename (direct + batch).
  - Drift computation with mixin awareness.
  - Sanity probe on the real codebase: ``training_enrollments`` (Session 80
    verified-clean) has no drift; ``incident_log`` (Session 79 design-blocked)
    has known critical drift.
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUDIT_PATH = _REPO_ROOT / "scripts" / "audit" / "column_drift_lite.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("column_drift_lite", _AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_AUDIT = _load_audit()


def _write_migration(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


def _collect_one(tmp_path: Path, name: str, body: str) -> dict[str, set[str]]:
    """Write a single migration into a tmp dir and run the collector on it.

    The collector walks ``MIGRATIONS_DIR`` so we monkeypatch via attribute
    swap — clean revert in a finally to avoid leaking state across tests.
    """
    mig = _write_migration(tmp_path, name, body)
    original = _AUDIT.MIGRATIONS_DIR
    _AUDIT.MIGRATIONS_DIR = mig.parent
    try:
        return _AUDIT.collect_migration_columns()
    finally:
        _AUDIT.MIGRATIONS_DIR = original


# ---------------------------------------------------------------------------
# Model-side: column extraction respects mapped_column vs relationship.
# ---------------------------------------------------------------------------


def test_is_column_value_accepts_mapped_column() -> None:
    import ast as _ast
    tree = _ast.parse("foo = mapped_column(String(64))")
    call = tree.body[0].value  # type: ignore[attr-defined]
    assert _AUDIT._is_column_value(call) is True


def test_is_column_value_rejects_relationship() -> None:
    import ast as _ast
    tree = _ast.parse('foo = relationship("Bar", backref="baz")')
    call = tree.body[0].value  # type: ignore[attr-defined]
    assert _AUDIT._is_column_value(call) is False


def test_is_column_value_accepts_attribute_form() -> None:
    import ast as _ast
    tree = _ast.parse("foo = sa.Column(sa.String(64))")
    call = tree.body[0].value  # type: ignore[attr-defined]
    assert _AUDIT._is_column_value(call) is True


# ---------------------------------------------------------------------------
# Migration-side: per-pattern column collection.
# ---------------------------------------------------------------------------


def test_direct_create_table_collects_columns(tmp_path: Path) -> None:
    result = _collect_one(
        tmp_path,
        "mig_create",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.create_table(
                "thing",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("name", sa.String(64), nullable=False),
                sa.Column("value", sa.Integer(), nullable=True),
            )
        """,
    )
    assert result["thing"] == {"id", "name", "value"}


def test_helper_wrapped_create_collects_explicit_and_injected_columns(tmp_path: Path) -> None:
    result = _collect_one(
        tmp_path,
        "mig_helper",
        """
        import sqlalchemy as sa
        from alembic import op
        def _base_columns():
            return [
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("tenant_id", sa.String(36), nullable=False),
            ]
        def _create_table(name, *cols):
            op.create_table(name, *cols, *_base_columns())
        def upgrade():
            _create_table("thing", sa.Column("custom_col", sa.String(64)))
        """,
    )
    assert result["thing"] == {"id", "tenant_id", "custom_col"}


def test_add_column_with_loop_credits_all_loop_values(tmp_path: Path) -> None:
    result = _collect_one(
        tmp_path,
        "mig_loop",
        """
        import sqlalchemy as sa
        from alembic import op
        _TABLES: tuple[str, ...] = ("alpha", "beta")
        def upgrade():
            for t in _TABLES:
                op.add_column(t, sa.Column("new_col", sa.Integer(), nullable=False))
        """,
    )
    assert result["alpha"] == {"new_col"}
    assert result["beta"] == {"new_col"}


def test_drop_column_removes_from_set(tmp_path: Path) -> None:
    result = _collect_one(
        tmp_path,
        "mig_drop",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.create_table("thing", sa.Column("keep", sa.String()), sa.Column("temp", sa.String()))
            op.drop_column("thing", "temp")
        """,
    )
    assert result["thing"] == {"keep"}


def test_alter_column_rename_replaces_old_with_new(tmp_path: Path) -> None:
    result = _collect_one(
        tmp_path,
        "mig_rename",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.create_table("thing", sa.Column("processed_at", sa.DateTime()))
            op.alter_column("thing", "processed_at", new_column_name="sent_at")
        """,
    )
    assert result["thing"] == {"sent_at"}
    assert "processed_at" not in result["thing"]


def test_batch_alter_table_handles_add_drop_rename(tmp_path: Path) -> None:
    result = _collect_one(
        tmp_path,
        "mig_batch",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.create_table("thing", sa.Column("orig", sa.String()), sa.Column("temp", sa.String()))
            with op.batch_alter_table("thing") as batch:
                batch.add_column(sa.Column("added", sa.Integer()))
                batch.drop_column("temp")
                batch.alter_column("orig", new_column_name="renamed")
        """,
    )
    assert result["thing"] == {"added", "renamed"}


# ---------------------------------------------------------------------------
# Drift computation with mixin awareness.
# ---------------------------------------------------------------------------


def test_compute_drift_subtracts_mixin_columns_from_both_sides() -> None:
    info = _AUDIT.ModelInfo(
        class_name="Foo",
        tablename="foo",
        columns={"id", "tenant_id", "created_at", "biz_col"},
        bases={"TenantBaseModel"},
    )
    models = {"foo": info}
    migration_cols = {"foo": {"biz_col"}}  # only biz_col; mixins not literal
    drift = _AUDIT.compute_drift(models, migration_cols)
    assert drift == []  # mixin cols don't count as drift


def test_compute_drift_reports_missing_business_column() -> None:
    info = _AUDIT.ModelInfo(
        class_name="Foo",
        tablename="foo",
        columns={"biz_a", "biz_b"},
        bases={"TenantBaseModel"},
    )
    models = {"foo": info}
    migration_cols = {"foo": {"biz_a"}}  # biz_b missing
    drift = _AUDIT.compute_drift(models, migration_cols)
    assert len(drift) == 1
    assert drift[0][1] == {"biz_b"}


# ---------------------------------------------------------------------------
# Model-side: mapped_column first-positional-arg DB name override.
# ---------------------------------------------------------------------------


def _load_models_from(tmp_path: Path, body: str) -> dict:
    """Write a synthetic models file into a tmp dir and run the model walker.

    Mirrors ``_collect_one`` (migrations) — swaps ``MODELS_FILE`` so the
    audit reads our synthetic content rather than the real codebase, then
    reverts in a finally so test isolation holds.
    """
    models_file = tmp_path / "synthetic_models.py"
    models_file.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    original = _AUDIT.MODELS_FILE
    _AUDIT.MODELS_FILE = models_file
    try:
        return _AUDIT.find_versioned_models()
    finally:
        _AUDIT.MODELS_FILE = original


def test_mapped_column_first_string_arg_resolves_to_db_column_name(tmp_path: Path) -> None:
    """``mapped_column("db_name", ...)`` overrides the Python attribute name.

    SQLAlchemy decouples Python attribute name from DB column name via the
    first positional string arg of ``mapped_column``. Real-world hit:
    ``Company.inn = mapped_column("tax_id", ...)`` — the migration creates
    column ``tax_id``; without resolving the override, the audit treats
    ``inn`` as missing and reports a false-positive drift.
    """
    models = _load_models_from(
        tmp_path,
        """
        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String

        class Foo(TenantBaseModel):
            __tablename__ = "foo"
            inn: Mapped[str | None] = mapped_column("tax_id", String(32), nullable=True)
            legal_address: Mapped[str | None] = mapped_column("address", String(255))
            plain: Mapped[str] = mapped_column(String(64), nullable=False)
        """,
    )
    foo = models["foo"]
    assert "tax_id" in foo.columns, (
        "first-arg string Constant should be resolved as DB column name"
    )
    assert "address" in foo.columns, "second override should also be resolved"
    assert "inn" not in foo.columns, (
        "Python attribute name must NOT leak when first-arg override is present"
    )
    assert "legal_address" not in foo.columns
    assert "plain" in foo.columns, (
        "plain mapped_column without first-string-arg keeps attribute name"
    )


def test_mapped_column_first_non_string_arg_keeps_attribute_name(tmp_path: Path) -> None:
    """``mapped_column(String(64), ...)`` and ``mapped_column(ForeignKey(...), ...)``
    have a Call/Name first arg, not a string Constant. Attribute name must
    be used as the DB column name — this is the existing behavior, pinned
    here as a regression guard against the override fix.
    """
    models = _load_models_from(
        tmp_path,
        """
        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String, ForeignKey, Integer

        class Bar(TenantBaseModel):
            __tablename__ = "bar"
            name: Mapped[str] = mapped_column(String(64), nullable=False)
            other_id: Mapped[str] = mapped_column(ForeignKey("other.id"), nullable=True)
            count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
        """,
    )
    bar = models["bar"]
    assert "name" in bar.columns
    assert "other_id" in bar.columns
    assert "count" in bar.columns


# ---------------------------------------------------------------------------
# Smoke probes against the real codebase.
# ---------------------------------------------------------------------------


def test_real_codebase_training_enrollments_has_no_drift() -> None:
    """Session 80 verified training_enrollments manually — must stay clean."""
    models = _AUDIT.find_versioned_models()
    migration_cols = _AUDIT.collect_migration_columns()
    assert "training_enrollments" in models
    info = models["training_enrollments"]
    model_business = info.columns - _AUDIT.MIXIN_COLUMNS
    mig_business = migration_cols.get("training_enrollments", set()) - _AUDIT.MIXIN_COLUMNS
    assert model_business <= mig_business, (
        f"Drift detected on training_enrollments: missing={sorted(model_business - mig_business)}"
    )


def test_real_codebase_incident_log_no_longer_critical_absent() -> None:
    """Session 79 documented incident_log as critical/absent (design-blocked).
    Closed by iter-42 (Session 89) — table is now created by migration
    ``20260529_iter42_incident_family.py``. This test inverts the original
    Session-80 assertion to be a regression guard against the table being
    accidentally removed from migrations again.
    """
    models = _AUDIT.find_versioned_models()
    migration_cols = _AUDIT.collect_migration_columns()
    assert "incident_log" in models
    # incident_log now exists in migrations with the business cols populated.
    assert "incident_log" in migration_cols, (
        "incident_log should be created by iter-42 — regression in migration coverage"
    )
    credited = migration_cols["incident_log"]
    business_cols = {"incident_id", "author_id", "stage", "status", "message", "metadata_json"}
    missing = business_cols - credited
    assert not missing, (
        f"incident_log missing business cols after iter-42: {sorted(missing)}"
    )


def test_real_codebase_no_unexpected_versioned_classes_missed() -> None:
    """Sanity: 111 versioned classes detected (matches Session 80 audit output)."""
    models = _AUDIT.find_versioned_models()
    # Loose floor — the project will add models; this just catches regressions
    # in the AST class detection (e.g. if the Mapped[...] detection breaks).
    assert len(models) >= 100, f"Only {len(models)} versioned classes — detection regression?"
