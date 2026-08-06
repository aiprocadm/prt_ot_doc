"""Audit-script regression tests for ``scripts/audit/version_column_drift.py``.

Pure AST analysis tests — no app imports, runs on any Python >= 3.10.

Covers:
  - v2 helper detection (regression guards added with this test file).
  - v3 loop-variable resolution (the gap documented in Session 79 handoff:
    iter-29's ``for table in _TABLES: op.add_column(table, sa.Column("version", ...))``
    pattern was silently dropped by the audit, leaving 8 drift tables
    uncredited even after the retrofit migration shipped).

The audit script is imported via ``importlib`` because it lives outside the
``backend`` package and is intentionally free of app-level imports (so it
runs on Win+Py3.13 where the full ``app.db.base`` chain hangs).
"""

from __future__ import annotations

import importlib.util
import textwrap
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AUDIT_PATH = _REPO_ROOT / "scripts" / "audit" / "version_column_drift.py"


def _load_audit():
    spec = importlib.util.spec_from_file_location("version_column_drift", _AUDIT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_AUDIT = _load_audit()


def _write_migration(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / f"{name}.py"
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# v3 RED tests — loop-variable resolution (currently fails before the fix).
# ---------------------------------------------------------------------------


def test_loop_with_module_const_annassign_tuple_credits_all_tables(tmp_path: Path) -> None:
    """iter-29 pattern: ``_TABLES: tuple[str, ...] = (...)`` + for-loop."""
    mig = _write_migration(
        tmp_path,
        "loop_annassign",
        """
        import sqlalchemy as sa
        from alembic import op
        _TABLES: tuple[str, ...] = ("alpha", "beta", "gamma")
        def upgrade():
            for t in _TABLES:
                op.add_column(t, sa.Column("version", sa.Integer(), nullable=False))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == {"alpha", "beta", "gamma"}


def test_loop_with_module_const_plain_tuple_credits_all_tables(tmp_path: Path) -> None:
    """Plain ``_TABLES = ("a", "b")`` assignment + for-loop."""
    mig = _write_migration(
        tmp_path,
        "loop_plain_tuple",
        """
        import sqlalchemy as sa
        from alembic import op
        _TABLES = ("alpha", "beta")
        def upgrade():
            for t in _TABLES:
                op.add_column(t, sa.Column("version", sa.Integer(), nullable=False))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == {"alpha", "beta"}


def test_loop_with_module_const_list_credits_all_tables(tmp_path: Path) -> None:
    """List form: ``_TABLES = ["a", "b"]``."""
    mig = _write_migration(
        tmp_path,
        "loop_list",
        """
        import sqlalchemy as sa
        from alembic import op
        _TABLES = ["alpha", "beta"]
        def upgrade():
            for t in _TABLES:
                op.add_column(t, sa.Column("version", sa.Integer(), nullable=False))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == {"alpha", "beta"}


def test_loop_with_inline_tuple_credits_all_tables(tmp_path: Path) -> None:
    """Inline iterable: ``for t in ("a", "b"):``."""
    mig = _write_migration(
        tmp_path,
        "loop_inline",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            for t in ("alpha", "beta"):
                op.add_column(t, sa.Column("version", sa.Integer(), nullable=False))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == {"alpha", "beta"}


def test_loop_with_unresolvable_iter_credits_nothing(tmp_path: Path) -> None:
    """``for t in get_tables():`` — can't resolve, don't credit anything."""
    mig = _write_migration(
        tmp_path,
        "loop_unresolvable",
        """
        import sqlalchemy as sa
        from alembic import op
        def get_tables(): return ()
        def upgrade():
            for t in get_tables():
                op.add_column(t, sa.Column("version", sa.Integer(), nullable=False))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == set()


def test_loop_with_non_version_column_credits_nothing(tmp_path: Path) -> None:
    """Loop adds a different column — must not credit ``version``."""
    mig = _write_migration(
        tmp_path,
        "loop_other_col",
        """
        import sqlalchemy as sa
        from alembic import op
        _TABLES = ("alpha", "beta")
        def upgrade():
            for t in _TABLES:
                op.add_column(t, sa.Column("note", sa.String(), nullable=True))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == set()


def test_iter29_actual_migration_credits_all_8_tables() -> None:
    """Integration: the real iter-29 file must credit all 8 retrofitted tables."""
    mig = (
        _REPO_ROOT
        / "backend"
        / "app"
        / "migrations"
        / "versions"
        / "20260528_iter29_version_retrofit_approval_edo.py"
    )
    expected = {
        "approval_decision_logs",
        "approval_instance_steps",
        "approval_processes",
        "approval_tasks",
        "edo_envelopes",
        "edo_status_events",
        "edo_webhook_inbox",
        "signature_requests",
    }
    assert _AUDIT._migration_creates_version(mig) == expected


# ---------------------------------------------------------------------------
# Regression tests — v1/v2 behavior must remain intact.
# ---------------------------------------------------------------------------


def test_literal_add_column_with_version_is_credited(tmp_path: Path) -> None:
    """Baseline: plain literal ``op.add_column("t", sa.Column("version", ...))`` still works."""
    mig = _write_migration(
        tmp_path,
        "literal",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.add_column("solo", sa.Column("version", sa.Integer(), nullable=False))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == {"solo"}


def test_direct_create_table_with_version_is_credited(tmp_path: Path) -> None:
    """Baseline: ``op.create_table("t", sa.Column("version", ...), ...)`` still works."""
    mig = _write_migration(
        tmp_path,
        "create_literal",
        """
        import sqlalchemy as sa
        from alembic import op
        def upgrade():
            op.create_table(
                "solo",
                sa.Column("id", sa.Integer(), primary_key=True),
                sa.Column("version", sa.Integer(), nullable=False),
            )
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == {"solo"}


def test_helper_wrapped_create_with_version_is_credited(tmp_path: Path) -> None:
    """v2 regression: helper that calls ``op.create_table`` and injects ``version``."""
    mig = _write_migration(
        tmp_path,
        "helper",
        """
        import sqlalchemy as sa
        from alembic import op
        def _create_table(name, *cols):
            op.create_table(name, *cols, sa.Column("version", sa.Integer(), nullable=False))
        def upgrade():
            _create_table("solo", sa.Column("id", sa.Integer(), primary_key=True))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == {"solo"}


def test_helper_wrapped_create_without_version_is_not_credited(tmp_path: Path) -> None:
    """Negative: helper does NOT inject ``version`` → table not credited."""
    mig = _write_migration(
        tmp_path,
        "helper_no_version",
        """
        import sqlalchemy as sa
        from alembic import op
        def _create_table(name, *cols):
            op.create_table(name, *cols)
        def upgrade():
            _create_table("solo", sa.Column("id", sa.Integer(), primary_key=True))
        """,
    )
    assert _AUDIT._migration_creates_version(mig) == set()
