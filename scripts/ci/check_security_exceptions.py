#!/usr/bin/env python3
"""Validate security exception metadata and reject expired records."""

from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import yaml


REQUIRED_FIELDS = ("id", "tool", "category", "owner", "reason", "expires_on")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exceptions-file",
        default=".github/security-exceptions.yml",
        help="Path to the security exception registry.",
    )
    return parser.parse_args()


def _load_exceptions(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"ERROR: exceptions file not found: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if payload is None:
        return []

    if not isinstance(payload, dict) or "exceptions" not in payload:
        raise SystemExit("ERROR: expected top-level mapping with key 'exceptions'.")

    exceptions = payload["exceptions"]
    if not isinstance(exceptions, list):
        raise SystemExit("ERROR: 'exceptions' must be a list.")

    return exceptions


def _parse_date(value: str, field_name: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError as exc:
        raise SystemExit(f"ERROR: invalid {field_name} date '{value}' (expected YYYY-MM-DD)") from exc


def validate_exceptions(exceptions: list[dict], today: dt.date) -> int:
    errors: list[str] = []

    for idx, item in enumerate(exceptions, start=1):
        if not isinstance(item, dict):
            errors.append(f"exception #{idx}: must be an object")
            continue

        missing = [field for field in REQUIRED_FIELDS if not item.get(field)]
        if missing:
            errors.append(f"exception #{idx}: missing required fields: {', '.join(missing)}")
            continue

        expires_on = _parse_date(str(item["expires_on"]), "expires_on")
        if expires_on < today:
            errors.append(
                "exception #{idx} ({id}): expired on {expires_on}".format(
                    idx=idx,
                    id=item["id"],
                    expires_on=expires_on.isoformat(),
                )
            )

        created_on = item.get("created_on")
        if created_on:
            _parse_date(str(created_on), "created_on")

    if errors:
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    print(f"Validated {len(exceptions)} security exception(s); no expired entries found.")
    return 0


def main() -> int:
    args = parse_args()
    exceptions = _load_exceptions(Path(args.exceptions_file))
    return validate_exceptions(exceptions, dt.date.today())


if __name__ == "__main__":
    raise SystemExit(main())
