#!/usr/bin/env python3
"""ARCH-4 guard — route refactors must keep the public OpenAPI contract identical.

Splitting god-route files into sub-routers (and extracting their helpers) must
NOT change the app's OpenAPI surface. This guard imports the FastAPI app, builds
``app.openapi()`` and fingerprints it, then compares to a baseline:

* **operations** — every ``METHOD path`` (e.g. ``GET /api/v1/documents``);
* **operationIds** — FastAPI's per-endpoint operation ids;
* **schemas** — component schema names.

A diff in any of these is a behaviour/contract change. Identical fingerprint =
the split was pure. (Ordering-sensitive path matching is a separate concern —
preserve endpoint registration order when splitting.)

Modes:
  --snapshot   capture the current fingerprint to the baseline JSON
               (run ONCE before a route refactor, on a known-good tree).
  (default)    compare current state to the baseline; exit 1 on any drift.

Baseline: docs/stabilization/openapi_routes_baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "docs" / "stabilization" / "openapi_routes_baseline.json"


def _collect() -> dict:
    from app.main import app  # full FastAPI app with all routers registered

    spec = app.openapi()
    operations: list[str] = []
    operation_ids: list[str] = []
    for path, methods in (spec.get("paths") or {}).items():
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete", "head", "options"}:
                continue
            operations.append(f"{method.upper()} {path}")
            if isinstance(op, dict) and op.get("operationId"):
                operation_ids.append(str(op["operationId"]))
    schema_map = (spec.get("components") or {}).get("schemas", {})
    schemas = sorted(schema_map.keys())
    # OPS-73 (разд. 73.1): подпись полей каждой схемы — {поле: тип}. Без неё
    # контрактный гейт видел бы только исчезновение схемы ЦЕЛИКОМ, а удаление
    # или смена типа поля (remove_field / change_type из API_BREAKING_CHANGES)
    # проходили бы зелёными.
    schema_fields: dict[str, dict[str, str]] = {}
    for name, schema in schema_map.items():
        if not isinstance(schema, dict):
            continue
        props = schema.get("properties")
        if not isinstance(props, dict):
            continue
        fields: dict[str, str] = {}
        for field_name, field_schema in props.items():
            if isinstance(field_schema, dict):
                if "type" in field_schema:
                    ftype = str(field_schema["type"])
                elif "$ref" in field_schema:
                    ftype = str(field_schema["$ref"]).rsplit("/", 1)[-1]
                elif "anyOf" in field_schema or "oneOf" in field_schema or "allOf" in field_schema:
                    variants = (
                        field_schema.get("anyOf")
                        or field_schema.get("oneOf")
                        or field_schema.get("allOf")
                    )
                    parts = []
                    for v in variants:
                        if isinstance(v, dict):
                            parts.append(
                                str(v.get("type") or str(v.get("$ref", "?")).rsplit("/", 1)[-1])
                            )
                    ftype = "|".join(sorted(parts))
                else:
                    ftype = "any"
            else:
                ftype = "any"
            fields[str(field_name)] = ftype
        schema_fields[name] = fields
    return {
        "operations": sorted(operations),
        "operation_ids": sorted(operation_ids),
        "schemas": schemas,
        "schema_fields": schema_fields,
        "openapi_version": spec.get("openapi", ""),
    }


def _snapshot() -> int:
    data = _collect()
    BASELINE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        f"✓ snapshot written: {BASELINE} "
        f"({len(data['operations'])} operations, {len(data['schemas'])} schemas)"
    )
    return 0


def _compare() -> int:
    if not BASELINE.exists():
        print(f"No baseline at {BASELINE}; run with --snapshot first.", file=sys.stderr)
        return 2
    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    cur = _collect()
    ok = True
    for key, label in (
        ("operations", "endpoints (METHOD path)"),
        ("operation_ids", "operationIds"),
        ("schemas", "component schemas"),
    ):
        added = sorted(set(cur[key]) - set(base[key]))
        removed = sorted(set(base[key]) - set(cur[key]))
        if added or removed:
            ok = False
            print(f"✖ ARCH-4: OpenAPI {label} changed:")
            for a in added:
                print(f"    + {a}")
            for r in removed:
                print(f"    - {r}")
    if ok:
        print(
            f"✓ ARCH-4: OpenAPI contract unchanged "
            f"({len(cur['operations'])} operations, {len(cur['schemas'])} schemas)."
        )
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--snapshot", action="store_true", help="capture the current OpenAPI as the baseline"
    )
    args = parser.parse_args()
    return _snapshot() if args.snapshot else _compare()


if __name__ == "__main__":
    raise SystemExit(main())
