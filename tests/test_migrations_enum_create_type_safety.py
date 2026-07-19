"""Pin-tests (regression guards): Alembic migrations must follow Postgres ENUM
safety rules.

Two classes of bug are pinned here. Both classes derive from one shared fact:
SQLAlchemy 2.x op-serialization treats ENUM creation inconsistently across
``op.create_table`` (auto-emits ``CREATE TYPE``) vs. ``op.add_column`` /
``batch.add_column`` (does NOT auto-emit). This asymmetry has been the source
of every Postgres alembic-upgrade failure since billing was restored on
2026-05-21.

Class 1 — enum double-create
----------------------------
Symptom:
    asyncpg.exceptions.DuplicateObjectError: type "<name>" already exists
    [SQL: CREATE TYPE <name> AS ENUM (...)]

Cause: migration calls ``<enum>.create(bind, checkfirst=True)`` AND also uses
``sa.Enum(name=X)`` (without ``create_type=False``) in a downstream
``op.create_table``/``op.add_column``. Auto-emission collides with the
explicit ``.create()``.

Fix: switch declaration to ``postgresql.ENUM(..., name=X, create_type=False)``.

Pin: ``test_no_migration_double_creates_enum_type``.

Class 3 — add_column without explicit create
--------------------------------------------
Symptom:
    asyncpg.exceptions.UndefinedObjectError: type "<name>" does not exist

Cause: migration uses ``sa.Enum(name=X)`` (or ``postgresql.ENUM``) inside an
``op.add_column``/``batch.add_column`` call but never calls ``.create()`` on
the type. ``op.add_column`` does NOT auto-emit CREATE TYPE — so the type is
never materialized in the database.

Fix: declare the enum as a variable (``postgresql.ENUM(..., create_type=False)``),
call ``var.create(op.get_bind(), checkfirst=True)`` BEFORE the first
``op.add_column``, and mirror with ``var.drop(...)`` in ``downgrade()``.

Pin: ``test_no_op_add_column_with_uncreated_enum``.

History
-------
* iter-7 (PRs #553/#554): first class-1 fix (one migration).
* iter-8 (PR #555): class-1 fix extended to 7 migrations.
* iter-9 (this PR #557): class-1 closed for 4 more migrations; class-1 pin
  added; class-2 (cross-branch dep) targeted fix for 20250501; class-3 pin
  added and corresponding fix for 20250601 (tenantkind).

Class 2 (cross-branch dependencies) is NOT pinned here — it would require an
Alembic DAG walker (`down_revision` chain + `depends_on` analysis). Deferred to
iter-10 if/when similar regressions surface.

Running locally without pytest (Windows+Py3.13 conftest hang workaround)
------------------------------------------------------------------------
    python tests/test_migrations_enum_create_type_safety.py

Exits 0 on no violations, 1 with a printed list otherwise.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "backend" / "app" / "migrations" / "versions"


@dataclass(frozen=True)
class Violation:
    file: str
    lineno: int
    enum_name: str
    call: str


def _func_lineno_range(tree: ast.Module, name: str) -> tuple[int, int] | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            end = getattr(node, "end_lineno", None)
            return node.lineno, end if end is not None else sys.maxsize
    return None


def _enum_call_kind(call: ast.Call) -> tuple[str, str] | None:
    """Return ("sa.Enum" | "postgresql.ENUM", name_kwarg) for matching calls.

    Returns None for unrelated calls or for calls without a string ``name=``.
    """
    func = call.func
    if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
        return None
    name_kw: str | None = None
    for kw in call.keywords:
        if (
            kw.arg == "name"
            and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str)
        ):
            name_kw = kw.value.value
    if name_kw is None:
        return None
    if func.attr == "Enum" and func.value.id == "sa":
        return ("sa.Enum", name_kw)
    if func.attr == "ENUM" and func.value.id == "postgresql":
        return ("postgresql.ENUM", name_kw)
    return None


def _has_create_type_false(call: ast.Call) -> bool:
    for kw in call.keywords:
        if (
            kw.arg == "create_type"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is False
        ):
            return True
    return False


def _is_non_native(call: ast.Call) -> bool:
    """True for ``native_enum=False`` declarations — these render as VARCHAR +
    CHECK and never emit ``CREATE TYPE``, so they cannot double-create. They are
    the SQLite side of a ``dialect == "postgresql"`` fork, where the Postgres
    side already carries ``create_type=False``.
    """
    for kw in call.keywords:
        if (
            kw.arg == "native_enum"
            and isinstance(kw.value, ast.Constant)
            and kw.value.value is False
        ):
            return True
    return False


def _uses_create_checkfirst(tree: ast.Module) -> bool:
    """True if the module contains any ``<expr>.create(..., checkfirst=True)`` call."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "create"):
            continue
        for kw in node.keywords:
            if (
                kw.arg == "checkfirst"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is True
            ):
                return True
    return False


def _audit_one(path: Path) -> list[Violation]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError as exc:
        return [
            Violation(
                file=str(path.relative_to(REPO_ROOT)),
                lineno=exc.lineno or 0,
                enum_name="<parse-error>",
                call=str(exc),
            )
        ]
    if not _uses_create_checkfirst(tree):
        return []
    downgrade_range = _func_lineno_range(tree, "downgrade")
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        match = _enum_call_kind(node)
        if match is None:
            continue
        call_str, enum_name = match
        if downgrade_range is not None and downgrade_range[0] <= node.lineno <= downgrade_range[1]:
            continue
        if _has_create_type_false(node) or _is_non_native(node):
            continue
        violations.append(
            Violation(
                file=str(path.relative_to(REPO_ROOT)),
                lineno=node.lineno,
                enum_name=enum_name,
                call=call_str,
            )
        )
    return violations


def _audit_migrations() -> list[Violation]:
    out: list[Violation] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        out.extend(_audit_one(path))
    return out


def test_no_migration_double_creates_enum_type() -> None:
    violations = _audit_migrations()
    if violations:
        lines = [f"  {v.file}:{v.lineno}  {v.call}(name={v.enum_name!r})" for v in violations]
        raise AssertionError(
            f"Found {len(violations)} ENUM declarations missing create_type=False "
            "in migrations that call .create(checkfirst=True). This double-creates "
            "the Postgres type and breaks alembic-postgres-upgrade. "
            "Fix per PR #555: switch the declaration to "
            "postgresql.ENUM(..., create_type=False). "
            "Downgrade .drop() calls may remain as sa.Enum.\n" + "\n".join(lines)
        )


def test_migrations_dir_exists() -> None:
    """Sanity: the audit target directory exists and contains migration files."""
    assert MIGRATIONS_DIR.is_dir(), f"missing migrations dir: {MIGRATIONS_DIR}"
    assert any(MIGRATIONS_DIR.glob("*.py")), "no *.py migrations found"


# ---------------------------------------------------------------------------
# Class 3: ENUM type used in op.add_column / batch.add_column without explicit
# .create() — op.add_column does NOT auto-emit CREATE TYPE, so the type is
# never materialized → UndefinedObjectError on first column access.
# ---------------------------------------------------------------------------


def _enum_names_in_add_column(tree: ast.Module) -> dict[str, int]:
    """Map of enum ``name`` → first lineno of usage inside any ``*.add_column(...)``
    call in upgrade scope. Covers both ``op.add_column`` and ``batch.add_column``."""
    downgrade_range = _func_lineno_range(tree, "downgrade")
    result: dict[str, int] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_column"):
            continue
        if downgrade_range is not None and downgrade_range[0] <= node.lineno <= downgrade_range[1]:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                match = _enum_call_kind(sub)
                if match is None:
                    continue
                _, enum_name = match
                result.setdefault(enum_name, sub.lineno)
    return result


def _enum_names_with_explicit_create(tree: ast.Module) -> set[str]:
    """Return set of enum ``name`` values for which an explicit ``<expr>.create(...)``
    call exists in upgrade scope.

    Handles two forms:
      1. inline: ``sa.Enum(name="X").create(bind, ...)``
      2. via variable: ``x = sa.Enum(name="X"); x.create(bind, ...)``

    Module-level assignments are included (var → name mapping holds anywhere in file).
    """
    downgrade_range = _func_lineno_range(tree, "downgrade")

    var_to_enum: dict[str, str] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)):
            continue
        match = _enum_call_kind(node.value)
        if match is None:
            continue
        _, enum_name = match
        for target in node.targets:
            if isinstance(target, ast.Name):
                var_to_enum[target.id] = enum_name

    created: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "create"):
            continue
        if downgrade_range is not None and downgrade_range[0] <= node.lineno <= downgrade_range[1]:
            continue
        # inline form: sa.Enum(...).create(...)
        if isinstance(func.value, ast.Call):
            match = _enum_call_kind(func.value)
            if match:
                _, enum_name = match
                created.add(enum_name)
        # variable form: var.create(...)
        elif isinstance(func.value, ast.Name) and func.value.id in var_to_enum:
            created.add(var_to_enum[func.value.id])
    return created


def _audit_one_class3(path: Path) -> list[Violation]:
    src = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    used_in_add = _enum_names_in_add_column(tree)
    if not used_in_add:
        return []
    created = _enum_names_with_explicit_create(tree)
    violations: list[Violation] = []
    for enum_name, lineno in sorted(used_in_add.items()):
        if enum_name in created:
            continue
        violations.append(
            Violation(
                file=str(path.relative_to(REPO_ROOT)),
                lineno=lineno,
                enum_name=enum_name,
                call="op.add_column without .create()",
            )
        )
    return violations


def _audit_migrations_class3() -> list[Violation]:
    out: list[Violation] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.py")):
        out.extend(_audit_one_class3(path))
    return out


def test_no_op_add_column_with_uncreated_enum() -> None:
    """Pin (class 3): any sa.Enum / postgresql.ENUM(name=X) used inside
    op.add_column(...) or batch.add_column(...) must have a corresponding
    <expr>.create(...) call in the same migration."""
    violations = _audit_migrations_class3()
    if violations:
        lines = [
            f"  {v.file}:{v.lineno}  type={v.enum_name!r}  used in op.add_column without <var>.create()"
            for v in violations
        ]
        raise AssertionError(
            f"Found {len(violations)} ENUM type(s) used in op.add_column without "
            "explicit .create(). op.add_column does NOT auto-emit CREATE TYPE on "
            "Postgres → UndefinedObjectError. Fix: declare as "
            "postgresql.ENUM(name=X, create_type=False) variable, call "
            "var.create(op.get_bind(), checkfirst=True) before op.add_column, "
            "mirror with var.drop(...) in downgrade.\n" + "\n".join(lines)
        )


if __name__ == "__main__":
    class1 = _audit_migrations()
    class3 = _audit_migrations_class3()
    if class1:
        print(f"VIOLATIONS (class 1: enum double-create), {len(class1)}:")
        for v in class1:
            print(f"  {v.file}:{v.lineno}  {v.call}(name={v.enum_name!r})")
    if class3:
        print(f"VIOLATIONS (class 3: op.add_column without .create()), {len(class3)}:")
        for v in class3:
            print(f"  {v.file}:{v.lineno}  type={v.enum_name!r}")
    if class1 or class3:
        sys.exit(1)
    print("OK — no enum migration safety violations found.")
    sys.exit(0)
