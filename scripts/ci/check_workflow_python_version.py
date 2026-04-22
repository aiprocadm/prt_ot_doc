#!/usr/bin/env python3
"""Fail CI if workflow Python versions drift from the canonical toolchain version."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = ROOT / ".github" / "workflows"
CANONICAL_PYTHON = "3.12"
PYTHON_VERSION_RE = re.compile(r'python-version:\s*["\']?([^"\']+)["\']?')


def main() -> int:
    violations: list[str] = []
    for workflow in sorted(WORKFLOWS_DIR.glob("*.yml")):
        for line_no, raw in enumerate(workflow.read_text(encoding="utf-8").splitlines(), start=1):
            match = PYTHON_VERSION_RE.search(raw)
            if not match:
                continue
            version = match.group(1).strip()
            if version != CANONICAL_PYTHON:
                violations.append(
                    f"{workflow.relative_to(ROOT)}:{line_no} python-version={version!r} "
                    f"(expected {CANONICAL_PYTHON!r})"
                )

    if violations:
        print("Workflow Python version drift detected:", file=sys.stderr)
        for item in violations:
            print(f" - {item}", file=sys.stderr)
        return 1

    print(f"Workflow Python version guard passed (all setup-python entries use {CANONICAL_PYTHON}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
