#!/usr/bin/env python3
"""Render ``--ignore-vuln`` CLI arguments for pip-audit from security exceptions.

pip-audit has no ignore-file mechanism (unlike trivy's ``.trivyignore``); the
only way to accept a finding is a repeated ``--ignore-vuln ID`` flag. This
script prints those flags for every ``tool: pip-audit`` exception so the CI
step can splice them into the command line:

    pip-audit ... $(python scripts/ci/render_pip_audit_ignores.py)

Expiry is NOT checked here on purpose: ``check_security_exceptions.py`` runs
earlier in the same workflow and fails the build on any expired record, so an
expired exception never reaches this renderer in a green pipeline.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exceptions-file", default=".github/security-exceptions.yml")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = yaml.safe_load(Path(args.exceptions_file).read_text(encoding="utf-8")) or {}
    exceptions = payload.get("exceptions", [])

    flags: list[str] = []
    for item in exceptions:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "pip-audit":
            continue
        identifier = str(item.get("id", "")).strip()
        # A vulnerability id is a single ``[A-Za-z0-9-]`` token (PYSEC-/GHSA-/CVE-);
        # refuse anything else so a malformed record cannot inject extra CLI words.
        if not identifier or not identifier.replace("-", "").isalnum():
            continue
        flags.append(f"--ignore-vuln {identifier}")

    print(" ".join(flags))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
