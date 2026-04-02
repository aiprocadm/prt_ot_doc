#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "backend" / "app"
ALLOWLIST = {
    "core/rbac_abac.py",
}


def main() -> int:
    violations: list[str] = []
    for path in TARGET.rglob("*.py"):
        rel = path.relative_to(TARGET).as_posix()
        if rel in ALLOWLIST:
            continue
        text = path.read_text(encoding="utf-8")
        if "session.query(" in text:
            violations.append(rel)

    if violations:
        print("Forbidden raw SQLAlchemy session.query(...) usage found:")
        for rel in violations:
            print(f" - backend/app/{rel}")
        return 1

    print("No forbidden session.query(...) usages found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
