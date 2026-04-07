#!/usr/bin/env python3
"""Fail CI if example env templates contain unsafe default secrets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

TARGETS = [
    ROOT / ".env.example",
    ROOT / "backend" / ".env.example",
]

FORBIDDEN_BY_KEY: dict[str, set[str]] = {
    "SECRET_KEY": {"change-me", "changeme", "secret", "test", "default"},
    "POSTGRES_PASSWORD": {"ptd", "postgres", "password", "admin", "change_me"},
    "S3_ACCESS_KEY": {"ptdminio", "minio", "test", "admin", "prt_local_access"},
    "S3_SECRET_KEY": {"ptdminio", "minioadmin", "test", "admin", "prt_local_secret"},
    "ADMIN_PASSWORD": {"admin123", "admin", "password", "123456", "qwerty"},
}

LINE_RE = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$")


def _normalize(value: str) -> str:
    return value.strip().strip('"').strip("'").strip().lower()


def main() -> int:
    violations: list[str] = []
    for target in TARGETS:
        if not target.exists():
            violations.append(f"{target}: file is missing")
            continue
        for line_no, raw in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = LINE_RE.match(raw)
            if not match:
                continue
            key, value = match.groups()
            if key not in FORBIDDEN_BY_KEY:
                continue
            normalized = _normalize(value)
            if not normalized:
                continue
            if normalized in FORBIDDEN_BY_KEY[key]:
                violations.append(f"{target.relative_to(ROOT)}:{line_no} {key} has forbidden default")

    if violations:
        print("Default secret guard failed:", file=sys.stderr)
        for item in violations:
            print(f" - {item}", file=sys.stderr)
        return 1

    print("Default secret guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
