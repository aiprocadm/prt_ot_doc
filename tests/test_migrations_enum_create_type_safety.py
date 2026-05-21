"""Pin-test (regression guard): Alembic migrations must not double-create Postgres
ENUM types.

Background
----------
SQLAlchemy 2.x op-serialization (``op.create_table`` / ``op.add_column`` with a
``sa.Enum(...)`` or ``postgresql.ENUM(...)`` column) loses the ``create_type``
attribute and re-emits ``CREATE TYPE`` without ``IF NOT EXISTS`` on Postgres.
When the migration ALSO calls ``<enum>.create(bind, checkfirst=True)``
explicitly, the second emission collides:

    asyncpg.exceptions.DuplicateObjectError: type "<name>" already exists
    [SQL: CREATE TYPE <name> AS ENUM (...)]

History of the fix
------------------
* iter-7 (PRs #553/#554): first fix on one migration.
* iter-8 (PR #555): extended the ``postgresql.ENUM(..., create_type=False)``
  pattern to 7 migrations that used ``.create(bind, checkfirst=True)``.
* iter-9 (this commit): closes the remaining migrations and pins the rule.

What this test enforces
-----------------------
For every migration under ``backend/app/migrations/versions/`` that contains at
least one ``X.create(..., checkfirst=True)`` call, every ``sa.Enum(name=...)``
or ``postgresql.ENUM(name=...)`` declaration *outside* the ``downgrade()``
function must have ``create_type=False`` set explicitly.

``downgrade()`` is excluded because the drop path uses
``sa.Enum(name=X).drop(bind, checkfirst=True)`` which does not need the value
list and is fine on the destructive path (PR #555 commit message documents
this exclusion explicitly).

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
        if _has_create_type_false(node):
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
        lines = [
            f"  {v.file}:{v.lineno}  {v.call}(name={v.enum_name!r})"
            for v in violations
        ]
        raise AssertionError(
            f"Found {len(violations)} ENUM declarations missing create_type=False "
            "in migrations that call .create(checkfirst=True). This double-creates "
            "the Postgres type and breaks alembic-postgres-upgrade. "
            "Fix per PR #555: switch the declaration to "
            "postgresql.ENUM(..., create_type=False). "
            "Downgrade .drop() calls may remain as sa.Enum.\n"
            + "\n".join(lines)
        )


def test_migrations_dir_exists() -> None:
    """Sanity: the audit target directory exists and contains migration files."""
    assert MIGRATIONS_DIR.is_dir(), f"missing migrations dir: {MIGRATIONS_DIR}"
    assert any(MIGRATIONS_DIR.glob("*.py")), "no *.py migrations found"


if __name__ == "__main__":
    vs = _audit_migrations()
    if vs:
        print(f"VIOLATIONS ({len(vs)}):")
        for v in vs:
            print(f"  {v.file}:{v.lineno}  {v.call}(name={v.enum_name!r})")
        sys.exit(1)
    print("OK — no enum double-create violations found.")
    sys.exit(0)
