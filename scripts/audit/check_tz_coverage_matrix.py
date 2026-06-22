#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

MATRIX_PATH = Path("docs/audit/TZ_COVERAGE_MATRIX.md")
REQUIRED_COLUMNS = [
    "REQ-ID",
    "requirement",
    "backend",
    "db",
    "jobs",
    "events",
    "frontend",
    "tests",
    "status",
    "priority",
    "plan",
]
ALLOWED_STATUS = {"done", "partial", "missing"}
ALLOWED_PRIORITY = {"p0", "p1", "p2"}


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def main() -> int:
    if not MATRIX_PATH.exists():
        print(f"ERROR: Matrix file not found: {MATRIX_PATH}")
        return 1

    lines = MATRIX_PATH.read_text(encoding="utf-8").splitlines()
    table_start = None
    headers: list[str] = []

    for idx, line in enumerate(lines):
        cells = _split_markdown_row(line)
        if not cells:
            continue
        if cells == REQUIRED_COLUMNS:
            table_start = idx
            headers = cells
            break

    if table_start is None:
        print("ERROR: Required table header not found or columns/order mismatch.")
        print(f"Expected: {REQUIRED_COLUMNS}")
        return 1

    errors: list[str] = []
    data_rows = 0
    seen_req_ids: dict[str, int] = {}

    for row_idx in range(table_start + 2, len(lines)):
        line = lines[row_idx].strip()
        if not line:
            break
        if not line.startswith("|"):
            break

        cells = _split_markdown_row(lines[row_idx])
        if not cells:
            continue
        if len(cells) != len(headers):
            errors.append(f"Line {row_idx + 1}: expected {len(headers)} columns, got {len(cells)}")
            continue

        row = dict(zip(headers, cells, strict=True))
        data_rows += 1

        for key in ("REQ-ID", "status", "priority"):
            if not row[key] or row[key] == "-":
                errors.append(f"Line {row_idx + 1}: '{key}' must be non-empty")

        req_id = row["REQ-ID"]
        if req_id and req_id != "-":
            if req_id in seen_req_ids:
                errors.append(
                    f"Line {row_idx + 1}: duplicate REQ-ID '{req_id}' "
                    f"(first seen at line {seen_req_ids[req_id] + 1})"
                )
            else:
                seen_req_ids[req_id] = row_idx

        status = row["status"].lower()
        if status not in ALLOWED_STATUS:
            errors.append(
                f"Line {row_idx + 1}: invalid status '{row['status']}' (allowed: {sorted(ALLOWED_STATUS)})"
            )

        priority = row["priority"].lower()
        if priority not in ALLOWED_PRIORITY:
            errors.append(
                f"Line {row_idx + 1}: invalid priority '{row['priority']}' (allowed: {sorted(ALLOWED_PRIORITY)})"
            )

    if data_rows == 0:
        errors.append("No data rows found under required header.")

    if errors:
        print("TZ coverage matrix validation FAILED:")
        for err in errors:
            print(f"- {err}")
        return 1

    print(
        f"TZ coverage matrix validation passed: {data_rows} rows, required columns and status/priority fields are valid."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
