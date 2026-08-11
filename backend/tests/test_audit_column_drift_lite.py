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

    iter-44: swaps ``MODELS_DIR`` (not the removed ``MODELS_FILE``) so the
    audit walks our tmp dir containing one synthetic file. Single-file
    semantics preserved: only one file written, so behaviorally equivalent
    to the pre-iter-44 contract. Reverts in a finally so test isolation holds.
    """
    models_file = tmp_path / "synthetic_models.py"
    models_file.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    original = _AUDIT.MODELS_DIR
    _AUDIT.MODELS_DIR = tmp_path
    try:
        return _AUDIT.find_versioned_models()
    finally:
        _AUDIT.MODELS_DIR = original


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


def _load_models_from_files(tmp_path: Path, files: dict[str, str]) -> dict:
    """Multi-file scope test helper for ``MODELS_DIR``-based walking (iter-44).

    Mirrors :func:`_load_models_from` but for the multi-file case: writes
    each ``filename: body`` pair into ``tmp_path`` and points
    ``_AUDIT.MODELS_DIR`` at the tmp dir so the audit walks all files.
    """
    for filename, body in files.items():
        (tmp_path / filename).write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    original = _AUDIT.MODELS_DIR
    _AUDIT.MODELS_DIR = tmp_path
    try:
        return _AUDIT.find_versioned_models()
    finally:
        _AUDIT.MODELS_DIR = original


def test_find_versioned_models_walks_all_files_in_models_dir(tmp_path: Path) -> None:
    """iter-44 multi-file scope: models in any *.py under MODELS_DIR are detected.

    Closes the 5th audit static-analysis blindspot (single-file MODELS_FILE
    scope, Session 93). Before iter-44 the audit scanned only ``models.py``,
    blind to ``approval_workflow.py``, ``job_engine.py``, ``risk.py``, etc.
    This test demonstrates models declared across multiple files are all
    found via the MODELS_DIR walk.
    """
    body_a = """
        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String

        class FooFromA(TenantBaseModel):
            __tablename__ = "foo_from_a"
            alpha: Mapped[str] = mapped_column(String(32))
    """
    body_b = """
        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String

        class BarFromB(TenantBaseModel):
            __tablename__ = "bar_from_b"
            beta: Mapped[str] = mapped_column(String(64))
    """
    models = _load_models_from_files(
        tmp_path,
        {"file_a.py": body_a, "file_b.py": body_b},
    )
    assert "foo_from_a" in models, (
        "model in file_a.py must be detected by multi-file walk"
    )
    assert "bar_from_b" in models, (
        "model in file_b.py must be detected by multi-file walk"
    )
    assert "alpha" in models["foo_from_a"].columns
    assert "beta" in models["bar_from_b"].columns


def test_find_versioned_models_skips_init_and_base_files(tmp_path: Path) -> None:
    """iter-44: ``__init__.py`` and ``base.py`` are skipped during multi-file walk.

    ``__init__.py`` typically only re-exports models; ``base.py`` defines
    the TenantBaseModel/SharedModel classes themselves (whose bases do NOT
    include the VERSIONED_BASES, so they would be filtered out anyway — but
    skipping by filename is a defensive cheap guard).
    """
    body_real = """
        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String

        class RealModel(TenantBaseModel):
            __tablename__ = "real_model"
            x: Mapped[str] = mapped_column(String(32))
    """
    body_noise = """
        from sqlalchemy.orm import Mapped, mapped_column
        from sqlalchemy import String

        # This model would be picked up if init.py wasn't skipped.
        class GhostFromInit(TenantBaseModel):
            __tablename__ = "ghost_from_init"
            y: Mapped[str] = mapped_column(String(32))
    """
    models = _load_models_from_files(
        tmp_path,
        {
            "real.py": body_real,
            "__init__.py": body_noise,
            "base.py": body_noise.replace("GhostFromInit", "GhostFromBase").replace(
                "ghost_from_init", "ghost_from_base"
            ),
        },
    )
    assert "real_model" in models
    assert "ghost_from_init" not in models, (
        "__init__.py models must be skipped — re-exports only by convention"
    )
    assert "ghost_from_base" not in models, (
        "base.py models must be skipped — only mixin/base classes live there"
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
    """Sanity: 186 versioned classes detected post-iter-44 multi-file scope.

    Pre-iter-44: ~111 classes (models.py only). Post-iter-44: 186 across all
    ``backend/app/models/*.py`` files. The 150 floor is the regression guard
    for the multi-file scope being preserved — if someone accidentally
    reverts to single-file ``MODELS_FILE``, the count drops back to ~111 and
    this test fires.
    """
    models = _AUDIT.find_versioned_models()
    assert len(models) >= 150, (
        f"Only {len(models)} versioned classes — multi-file scope regression "
        f"(iter-44 should detect 180+ across all model files)?"
    )


# ---------------------------------------------------------------------------
# Dynamic batch_alter_table table-name resolution (iter-39).
#
# Closes the fourth audit static-analysis blindspot. Pattern in real
# migration `8d2c1a6c5e24_domain_normalization.py`:
#
#     def _resolve_npa_binding_table(bind) -> str | None:
#         if inspector.has_table("npa_binding"): return "npa_binding"
#         if inspector.has_table("npabinding"):  return "npabinding"
#         return None
#
#     def upgrade():
#         npa_binding_table = _resolve_npa_binding_table(bind)
#         if npa_binding_table:
#             with op.batch_alter_table(npa_binding_table, schema=None) as batch:
#                 batch.add_column(sa.Column("entity_type", ...))
#                 batch.add_column(sa.Column("entity_id", ...))
#                 batch.add_column(sa.Column("context", ...))
#
# Pre-iter-39 the audit only handled `batch_alter_table("<literal>", ...)`
# (the first arg as ast.Constant). Variable form was silently skipped →
# false-positive drift on 3 cols for npabinding.
#
# Mirrors prior audit-correctness passes per `[[audit-static-analysis-blindspots]]`:
#   - Session 79: helper-wrapped create_table
#   - Session 81: mapped_column first-arg name override
#   - Session 85: alter_column server_default form
# ---------------------------------------------------------------------------


def test_batch_alter_table_dynamic_name_resolved_via_function_return_literals(
    tmp_path: Path,
) -> None:
    """Variable bound to a function returning multiple string literals: credit
    cols to ALL possible returns. Mirror of `_resolve_npa_binding_table`.
    """
    result = _collect_one(
        tmp_path,
        "mig_dynamic_batch",
        """
        import sqlalchemy as sa
        from alembic import op
        def _resolve_table(bind):
            if bind.has_table("alpha"):
                return "alpha"
            if bind.has_table("beta"):
                return "beta"
            return None
        def upgrade():
            bind = op.get_bind()
            tname = _resolve_table(bind)
            if tname:
                with op.batch_alter_table(tname, schema=None) as batch:
                    batch.add_column(sa.Column("new_col", sa.String(36)))
        """,
    )
    assert result["alpha"] == {"new_col"}
    assert result["beta"] == {"new_col"}


def test_batch_alter_table_dynamic_name_single_return_literal(tmp_path: Path) -> None:
    """Resolver returns one string literal: credit to that single table."""
    result = _collect_one(
        tmp_path,
        "mig_dynamic_single",
        """
        import sqlalchemy as sa
        from alembic import op
        def _get_name():
            return "only_table"
        def upgrade():
            tname = _get_name()
            with op.batch_alter_table(tname, schema=None) as batch:
                batch.add_column(sa.Column("col_a", sa.String(36)))
        """,
    )
    assert result["only_table"] == {"col_a"}


def test_batch_alter_table_dynamic_name_unresolvable_does_not_crash(tmp_path: Path) -> None:
    """Var bound to a Call whose callee isn't in the same module's functions:
    must skip block silently — no crash, no phantom credits.
    """
    result = _collect_one(
        tmp_path,
        "mig_dynamic_untraceable",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            tname = some_undefined_callable()  # not in module's functions
            with op.batch_alter_table(tname, schema=None) as batch:
                batch.add_column(sa.Column("ghost", sa.String(36)))
        """,
    )
    assert all("ghost" not in cols for cols in result.values()), (
        "unresolvable dynamic table name must not credit cols anywhere"
    )


def test_batch_alter_table_dynamic_name_resolver_skips_none_returns(tmp_path: Path) -> None:
    """Resolver mixing string and `return None`: only string literals counted.
    Direct parity with `_resolve_npa_binding_table` (None for the missing-
    table case).
    """
    result = _collect_one(
        tmp_path,
        "mig_dynamic_with_none",
        """
        import sqlalchemy as sa
        from alembic import op
        def _resolve(bind):
            if bind:
                return "gamma"
            return None
        def upgrade():
            t = _resolve(op.get_bind())
            if t:
                with op.batch_alter_table(t, schema=None) as batch:
                    batch.add_column(sa.Column("only_col", sa.Integer()))
        """,
    )
    assert result["gamma"] == {"only_col"}
    # None must not have been treated as a phantom table key.
    assert None not in result


def test_batch_alter_table_dynamic_name_supports_drop_and_rename(tmp_path: Path) -> None:
    """drop_column + alter_column rename inside a dynamic-name batch block:
    must work for ALL resolved table names symmetrically with the literal-
    name path.
    """
    result = _collect_one(
        tmp_path,
        "mig_dynamic_drop_rename",
        """
        import sqlalchemy as sa
        from alembic import op
        def _names():
            return "alpha"
        def upgrade():
            op.create_table("alpha", sa.Column("orig", sa.String()), sa.Column("temp", sa.String()))
            t = _names()
            with op.batch_alter_table(t, schema=None) as batch:
                batch.add_column(sa.Column("added", sa.Integer()))
                batch.drop_column("temp")
                batch.alter_column("orig", new_column_name="renamed")
        """,
    )
    assert result["alpha"] == {"added", "renamed"}


def test_real_codebase_npabinding_no_longer_flagged() -> None:
    """Closed-loop: after iter-39 audit extension, npabinding's 3 cols
    (`context`, `entity_id`, `entity_type`) are credited via the dynamic
    `_resolve_npa_binding_table()` resolution path in
    `8d2c1a6c5e24_domain_normalization.py`.
    """
    models = _AUDIT.find_versioned_models()
    migration_cols = _AUDIT.collect_migration_columns()
    assert "npabinding" in models
    info = models["npabinding"]
    model_business = info.columns - _AUDIT.MIXIN_COLUMNS
    mig_business = migration_cols.get("npabinding", set()) - _AUDIT.MIXIN_COLUMNS
    assert {"context", "entity_id", "entity_type"} <= mig_business, (
        f"Expected dynamic batch_alter_table resolution to credit "
        f"context/entity_id/entity_type to npabinding; "
        f"got mig_business={sorted(mig_business)}"
    )
    assert model_business <= mig_business, (
        f"npabinding drift after iter-39: "
        f"missing={sorted(model_business - mig_business)}"
    )


def test_real_codebase_npabinding_cleared_from_drift_after_iter39() -> None:
    """Closed-loop scoped to iter-39's contribution: npabinding's false
    positive must be cleared by the dynamic-batch_alter_table resolution.

    Originally pinned an exact "expected_remaining" set (5 tables) as the
    state after iter-39. That worked while iter-39 was the only landing.
    iter-40 / iter-41 / iter-42 each subsequently close another table —
    when ALL four land together, the equality assertion fails because
    drift_tables == empty set. Relaxed to "npabinding is cleared", which
    holds across any combination of follow-up iters. Integration-level
    "all drift cleared" assertion is owned by iter-42's closed-loop test.
    """
    models = _AUDIT.find_versioned_models()
    migration_cols = _AUDIT.collect_migration_columns()
    drift = _AUDIT.compute_drift(models, migration_cols)
    drift_tables = {info.tablename for info, _missing in drift}
    assert "npabinding" not in drift_tables, (
        "npabinding must be cleared by iter-39 dynamic-batch resolution"
    )


# ---------------------------------------------------------------------------
# Helper-function unit tests for the new audit primitives.
# ---------------------------------------------------------------------------


def test_function_return_literals_collects_all_string_returns() -> None:
    import ast as _ast
    src = textwrap.dedent("""
        def f(x):
            if x == 1:
                return "alpha"
            if x == 2:
                return "beta"
            return None
    """).lstrip()
    func = _ast.parse(src).body[0]
    assert _AUDIT._function_return_literals(func) == {"alpha", "beta"}


def test_function_return_literals_ignores_non_string_returns() -> None:
    import ast as _ast
    src = textwrap.dedent("""
        def f():
            if True:
                return 42
            if False:
                return some_var
            return None
    """).lstrip()
    func = _ast.parse(src).body[0]
    assert _AUDIT._function_return_literals(func) == set()


def test_resolve_dynamic_name_traces_call_to_module_function() -> None:
    import ast as _ast
    src = textwrap.dedent("""
        def _helper():
            return "tbl_x"
        def upgrade():
            tname = _helper()
            with op.batch_alter_table(tname) as batch:
                pass
    """).lstrip()
    tree = _ast.parse(src)
    functions = {n.name: n for n in tree.body if isinstance(n, _ast.FunctionDef)}
    upgrade = functions["upgrade"]
    resolved = _AUDIT._resolve_dynamic_name_from_assignments(
        "tname", upgrade, functions
    )
    assert resolved == ["tbl_x"]


def test_resolve_dynamic_name_returns_empty_when_var_not_assigned() -> None:
    import ast as _ast
    src = textwrap.dedent("""
        def upgrade():
            with op.batch_alter_table(other_name) as batch:
                pass
    """).lstrip()
    tree = _ast.parse(src)
    functions = {n.name: n for n in tree.body if isinstance(n, _ast.FunctionDef)}
    resolved = _AUDIT._resolve_dynamic_name_from_assignments(
        "other_name", functions["upgrade"], functions
    )
    assert resolved == []
