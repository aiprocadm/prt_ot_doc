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

    lines = ["# Generated from .github/security-exceptions.yml; do not edit manually."]
    for item in exceptions:
        if not isinstance(item, dict):
            continue
        if item.get("tool") != "trivy":
            continue
        if item.get("category") != "vulnerability":
            continue

        identifier = str(item.get("id", "")).strip()
        if not identifier:
            continue

        expires_on = item.get("expires_on", "unknown")
        owner = item.get("owner", "unknown")
        lines.append(f"{identifier} # owner={owner} expires_on={expires_on}")

    Path(args.output).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
