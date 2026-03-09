#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from app.db import Base


@dataclass
class SchemaCheckResult:
    missing_tenant_id: list[str]
    missing_foreign_keys: list[str]
    tables_without_primary_key: list[str]
    nullable_status_columns: list[str]


def run_checks() -> SchemaCheckResult:
    ignored_shared_tables = {
        "tenant",
        "alembic_version",
        "billing_plan",
        "feature_flag",
        "outbox_subscription",
    }

    missing_tenant_id: list[str] = []
    missing_foreign_keys: list[str] = []
    tables_without_primary_key: list[str] = []
    nullable_status_columns: list[str] = []

    for table in Base.metadata.sorted_tables:
        if not table.primary_key.columns:
            tables_without_primary_key.append(table.name)

        if table.name not in ignored_shared_tables and table.name != "audit_log":
            if "tenant_id" not in table.columns:
                missing_tenant_id.append(table.name)

        for col in table.columns:
            if col.name.endswith("_id") and col.name not in {"id", "tenant_id"}:
                if not col.foreign_keys:
                    missing_foreign_keys.append(f"{table.name}.{col.name}")
            if col.name == "status" and col.nullable:
                nullable_status_columns.append(f"{table.name}.status")

    return SchemaCheckResult(
        missing_tenant_id=sorted(set(missing_tenant_id)),
        missing_foreign_keys=sorted(set(missing_foreign_keys)),
        tables_without_primary_key=sorted(set(tables_without_primary_key)),
        nullable_status_columns=sorted(set(nullable_status_columns)),
    )


def main() -> int:
    result = run_checks()
    payload = asdict(result)
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    has_errors = bool(result.missing_tenant_id or result.tables_without_primary_key)
    return 1 if has_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
