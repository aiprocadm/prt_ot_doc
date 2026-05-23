#!/usr/bin/env python3
"""Render a Trivy ignore file from security exceptions metadata."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exceptions-file", default=".github/security-exceptions.yml")
    parser.add_argument("--output", default=".trivyignore.generated")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = yaml.safe_load(Path(args.exceptions_file).read_text(encoding="utf-8")) or {}
    exceptions = payload.get("exceptions", [])

    # Trivy reads a single ``.trivyignore.generated`` file regardless of which
    # scan emits the finding (dependency scan, container image scan, ...). The
    # security-exceptions schema groups entries by ``category`` (vulnerability,
    # container, ...) for human readability and reporting, but at the trivy
    # ignore layer those categories all flow through the same file. Emit every
    # ``tool: trivy`` exception irrespective of category, otherwise a
    # ``category: container`` entry (e.g. CVE-2025-62727 starlette DoS in the
    # container image) is silently dropped and the container-image-scan job
    # fails for an already-accepted finding.
    _TRIVY_CATEGORIES = {"vulnerability", "container"}

    lines = ["# Generated from .github/security-exceptions.yml; do not edit manually."]
    for item in exceptions:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "trivy":
            continue
        if item.get("category") not in _TRIVY_CATEGORIES:
            continue

        identifier = str(item.get("id", "")).strip()
        if not identifier:
            continue

        expires_on = item.get("expires_on", "unknown")
        owner = item.get("owner", "unknown")
        category = item.get("category", "unknown")
        lines.append(f"{identifier} # owner={owner} category={category} expires_on={expires_on}")

    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
