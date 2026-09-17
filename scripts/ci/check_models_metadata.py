#!/usr/bin/env python3
"""ARCH-2 guard — model decomposition must be behaviour/schema/contract preserving.

Splitting the god-file ``backend/app/models/models.py`` into domain files is a
PURE MOVE of class definitions: the DB schema must not change and every name
that was importable before must stay importable. This guard makes that fast to
verify (no PG, no full suite, ~15s):

1. ``configure_mappers()`` — proves no circular import / unresolved relationship
   was introduced by the move.
2. **Metadata fingerprint** — table -> sorted(column name, column type) for
   SharedBase + TenantBase. Identical before/after a pure move; a diff here is a
   would-be ``alembic autogenerate`` diff.
3. **Re-export completeness** — every name in ``app.models.__all__`` and
   ``app.models.models.__all__`` still resolves on its module.

Modes:
  --snapshot   capture the current fingerprint+names to the baseline JSON
               (run ONCE before the first move, on a known-good tree).
  (default)    compare current state to the baseline; exit 1 on any drift.

Baseline: docs/stabilization/models_metadata_baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "docs" / "stabilization" / "models_metadata_baseline.json"


def _collect() -> dict:
    from sqlalchemy.orm import configure_mappers

    import app.db.base  # noqa: F401  triggers all model imports (incl. app.modules.*)
    from app.db.session import SharedBase, TenantBase

    configure_mappers()  # raises if the move broke a mapper/relationship

    fingerprint: dict[str, list[list[str]]] = {}
    for base in (SharedBase, TenantBase):
        for table in base.metadata.tables.values():
            cols = sorted([col.name, str(col.type)] for col in table.columns)
            # Bare table name is unique across both bases in this schema.
            fingerprint[table.name] = cols

    import enum as _enum

    import app.models as models_pkg
    import app.models.models as models_mod

    init_names = sorted(getattr(models_pkg, "__all__", []))
    models_names = sorted(getattr(models_mod, "__all__", []))

    missing = []
    for name in init_names:
        if not hasattr(models_pkg, name):
            missing.append(f"app.models.{name}")
    for name in models_names:
        if not hasattr(models_mod, name):
            missing.append(f"app.models.models.{name}")

    # Every ORM model / Enum importable from app.models.models — broader than
    # __all__. A pure move + re-export must NOT drop any of these (this is what
    # catches a re-export accidentally stripped by ruff F401, which __all__ alone
    # would miss).
    def _is_public_type(obj: object) -> bool:
        return isinstance(obj, type) and (
            hasattr(obj, "__tablename__") or issubclass(obj, _enum.Enum)
        )

    models_types = sorted(
        n
        for n in dir(models_mod)
        if not n.startswith("_") and _is_public_type(getattr(models_mod, n, None))
    )

    return {
        "tables": dict(sorted(fingerprint.items())),
        "init_all": init_names,
        "models_all": models_names,
        "models_public_types": models_types,
        "unresolved_names": missing,
    }


def _snapshot() -> int:
    data = _collect()
    if data["unresolved_names"]:
        print("Refusing to snapshot — unresolved re-export names:", file=sys.stderr)
        for n in data["unresolved_names"]:
            print(f"  {n}", file=sys.stderr)
        return 1
    payload = {k: v for k, v in data.items() if k != "unresolved_names"}
    BASELINE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"✓ snapshot written: {BASELINE} ({len(payload['tables'])} tables)")
    return 0


def _compare() -> int:
    if not BASELINE.exists():
        print(f"No baseline at {BASELINE}; run with --snapshot first.", file=sys.stderr)
        return 2
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    cur = _collect()
    ok = True

    if cur["unresolved_names"]:
        ok = False
        print("✖ ARCH-2: re-export names no longer resolve (import contract broken):")
        for n in cur["unresolved_names"]:
            print(f"    {n}")

    # Schema fingerprint diff (== alembic autogenerate diff).
    base_tables = base["tables"]
    cur_tables = cur["tables"]
    added = sorted(set(cur_tables) - set(base_tables))
    removed = sorted(set(base_tables) - set(cur_tables))
    changed = sorted(
        t for t in set(cur_tables) & set(base_tables) if cur_tables[t] != base_tables[t]
    )
    if added or removed or changed:
        ok = False
        print("✖ ARCH-2: schema fingerprint changed (move was NOT pure / would alter migrations):")
        for t in added:
            print(f"    + table {t}")
        for t in removed:
            print(f"    - table {t}")
        for t in changed:
            print(f"    ~ table {t} columns differ")

    # Public names must be a SUPERSET of the baseline (never lose a name).
    for key, label in (("init_all", "app.models"), ("models_all", "app.models.models")):
        lost = sorted(set(base[key]) - set(cur[key]))
        if lost:
            ok = False
            print(f"✖ ARCH-2: {label} stopped exporting names:")
            for n in lost:
                print(f"    {n}")

    # Every model/Enum type importable from app.models.models at baseline must
    # remain importable (catches re-exports silently dropped by ruff F401).
    base_types = base.get("models_public_types")
    if base_types is not None:
        lost_types = sorted(set(base_types) - set(cur.get("models_public_types", [])))
        if lost_types:
            ok = False
            print("✖ ARCH-2: app.models.models stopped exporting model/Enum types:")
            for n in lost_types:
                print(f"    {n}")

    if ok:
        print(
            f"✓ ARCH-2: schema + re-exports unchanged "
            f"({len(cur_tables)} tables, {len(cur['init_all'])} app.models names)."
        )
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--snapshot", action="store_true", help="capture the current state as the baseline"
    )
    args = parser.parse_args()
    return _snapshot() if args.snapshot else _compare()


if __name__ == "__main__":
    raise SystemExit(main())
