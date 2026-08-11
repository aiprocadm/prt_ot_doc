"""Pin tests for iter-29 ``version`` column retrofit on 8 approval/EDO tables.

iter-29 RB-002s (mixin-retrofit drift class — column declared by
``VersionedMixin`` but absent from creator migration). Discovered via
``scripts/audit/version_column_drift.py``.

Each of the 8 tables inherits ``TenantBaseModel`` which mixes in
``VersionedMixin``. The mixin sets ``__mapper_args__["version_id_col"] =
cls.version``, activating SQLAlchemy optimistic concurrency control.
Without a DDL-level ``version`` column, every ORM UPDATE crashes on
Postgres (``UndefinedColumnError``); SQLite silently degrades because
the dialect falls back to plain UPDATE when the version_id_col target
column is missing.

These tests guard:
  - ORM side: each of the 8 model classes still exposes ``version``.
  - Migration side: iter-29 chains to iter-26 head and adds the column
    on exactly the 8 expected tables.
  - Regression guard: VersionedMixin remains wired into ``TenantBaseModel``
    (so future audits keep flagging same-class drift the same way).
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.models.base import TenantBaseModel, VersionedMixin
from app.models.models import (
    ApprovalDecisionLog,
    ApprovalInstanceStep,
    ApprovalProcess,
    ApprovalTask,
    EdoStatusEvent,
    EdoWebhookInbox,
    SignatureRequest,
)

# Tuple of (ORM model class, DDL table name) — both halves of the contract.
# NOTE (ed02, 2026-06-12): EdoEnvelope удалён из ORM, а таблица edo_envelopes
# дропнута миграцией 20260612_ed02_drop_legacy_signing_tables. Историческая
# iter-29 миграция НЕ редактируется (она уже применена в проде) — её _TABLES
# по-прежнему содержит "edo_envelopes"; см. _MIGRATION_TABLES ниже.
_COHORT = [
    (ApprovalDecisionLog, "approval_decision_logs"),
    (ApprovalInstanceStep, "approval_instance_steps"),
    (ApprovalProcess, "approval_processes"),
    (ApprovalTask, "approval_tasks"),
    (EdoStatusEvent, "edo_status_events"),
    (EdoWebhookInbox, "edo_webhook_inbox"),
    (SignatureRequest, "signature_requests"),
]

# Migration-side cohort: исторический состав iter-29 (включая дропнутую позже
# таблицу edo_envelopes — ed02 идёт ПОСЛЕ iter-29 в цепочке, поэтому ретрофит
# на тот момент был корректен и обязан остаться нетронутым).
_MIGRATION_TABLES = {tablename for _, tablename in _COHORT} | {"edo_envelopes"}


@pytest.mark.parametrize(("model", "tablename"), _COHORT)
def test_model_has_version_column(model, tablename) -> None:
    columns = inspect(model).columns
    assert "version" in columns, (
        f"{model.__name__} must expose `version` from VersionedMixin; "
        f"if removed, SQLAlchemy optimistic locking on {tablename} "
        "silently degrades and iter-29 migration becomes orphaned"
    )


@pytest.mark.parametrize(("model", "tablename"), _COHORT)
def test_version_column_is_integer_not_null(model, tablename) -> None:
    column = inspect(model).columns["version"]
    assert not column.nullable, (
        f"{tablename}.version must be NOT NULL — VersionedMixin "
        "declares it nullable=False; optimistic-lock semantics rely on "
        "every row having an integer to compare against"
    )
    # Type check: Integer subclass (SQLAlchemy may wrap as BigInteger etc.).
    assert (
        column.type.python_type is int
    ), f"{tablename}.version must be Integer-typed; got {column.type!r}"


@pytest.mark.parametrize(("model", "_tablename"), _COHORT)
def test_version_id_col_wired_in_mapper(model, _tablename) -> None:
    # __mapper_args__["version_id_col"] is what activates SQLAlchemy
    # optimistic locking. If a future refactor decouples VersionedMixin's
    # column declaration from this mapper-side wiring, the column stays
    # but every UPDATE silently loses the WHERE version=<old> guard —
    # very subtle regression. Pin both halves of the contract.
    mapper = inspect(model)
    vid_col = mapper.version_id_col
    assert vid_col is not None, (
        f"{model.__name__} mapper lost version_id_col binding — " "VersionedMixin contract broken"
    )
    assert vid_col.name == "version"


def test_tenant_base_model_inherits_versioned_mixin() -> None:
    # If this fails, the *whole class* of drift fixed by iter-29 disappears
    # (some models would no longer have version, others would, audit logic
    # no longer applies). Forces conscious decision rather than silent drop.
    assert issubclass(TenantBaseModel, VersionedMixin), (
        "TenantBaseModel must inherit VersionedMixin — the entire "
        "iter-29 cohort assumes this. If removed, audit "
        "version_column_drift.py needs rewriting and this test deleted "
        "as a coordinated decision."
    )


# ---- Migration-side guards --------------------------------------------------


def _load_iter29_migration():
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260528_iter29_version_retrofit_approval_edo.py"
    )
    assert migration_path.exists(), f"iter-29 migration file missing at {migration_path}"
    spec = importlib.util.spec_from_file_location("iter29_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_iter29_migration_chains_to_iter26_head() -> None:
    module = _load_iter29_migration()
    assert module.revision == "20260528_iter29_version_retrofit"
    # iter-27 and iter-28 were app-code only (no migration), so iter-26
    # remains the true head until iter-29 lands.
    assert module.down_revision == "20260527_iter26_inspection_result", (
        f"iter-29 down_revision drift: got {module.down_revision!r}; "
        "expected '20260527_iter26_inspection_result'. See [[alembic-heads-lesson]]."
    )


def test_iter29_migration_table_cohort_matches_expected() -> None:
    module = _load_iter29_migration()
    actual = set(module._TABLES)
    assert actual == _MIGRATION_TABLES, (
        f"iter-29 cohort drift. Migration touches: {actual}. "
        f"Historical cohort expects: {_MIGRATION_TABLES}. "
        "iter-29 — историческая миграция: её _TABLES не редактируется; "
        "если ORM-когорта меняется (модель удалена + таблица дропнута "
        "последующей миграцией, как edo_envelopes/ed02), правь _COHORT и "
        "_MIGRATION_TABLES в этом тесте."
    )


def test_iter29_adds_only_version_column() -> None:
    # Scope-guard. The migration must be a pure mixin-retrofit; if a
    # future edit sneaks in other columns or constraints, this test
    # forces splitting the iter. AST-scoped to the upgrade() function
    # so docstring mentions of `sa.Column(...)` (e.g. explaining the
    # fix pattern) don't trigger a false positive.
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "migrations"
        / "versions"
        / "20260528_iter29_version_retrofit_approval_edo.py"
    )
    tree = ast.parse(migration_path.read_text(encoding="utf-8"))
    upgrade_fn = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"),
        None,
    )
    assert upgrade_fn is not None, "iter-29 migration missing upgrade()"
    column_calls: list[str] = []
    create_table_count = 0
    for node in ast.walk(upgrade_fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "Column"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            column_calls.append(node.args[0].value)
        if isinstance(func, ast.Attribute) and func.attr == "create_table":
            create_table_count += 1
    assert column_calls == ["version"], (
        f"iter-29 must only add a `version` column; found Column() "
        f"calls in upgrade() for: {column_calls}. "
        "If you need to add other columns, use a separate iter."
    )
    assert create_table_count == 0, (
        "iter-29 is a column-retrofit iter, not a table-creation iter. "
        "If you need to create a table, use a separate iter."
    )


def test_iter29_upgrade_and_downgrade_are_inverse() -> None:
    module = _load_iter29_migration()
    assert tuple(sorted(module._TABLES)) == tuple(sorted(_MIGRATION_TABLES))
    # ``_TABLES`` is the single source of truth in the migration — both
    # ``upgrade()`` (forward) and ``downgrade()`` (reversed) iterate it,
    # so symmetry is structural. Pin the tuple shape so a future edit
    # that reorders one path without the other is caught.
    assert isinstance(module._TABLES, tuple)
    assert len(module._TABLES) == 8
