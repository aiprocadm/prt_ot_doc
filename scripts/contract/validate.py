"""Lightweight OpenAPI contract validation based on static analysis."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


def _load_spec(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise SystemExit("OpenAPI specification must deserialize into an object")
    return data


def main() -> None:
    """Ensure the bundled OpenAPI document is well-formed and non-empty."""

    spec_path = Path(os.environ.get("OPENAPI_SPEC_PATH", "openapi.yaml")).resolve()
    if not spec_path.exists():
        raise SystemExit(f"OpenAPI specification not found: {spec_path}")

    spec = _load_spec(spec_path)
    version = str(spec.get("openapi") or spec.get("swagger") or "")
    paths = spec.get("paths")
    if not isinstance(paths, dict) or not paths:
        raise SystemExit("OpenAPI specification is missing path definitions")

    operations: list[tuple[str, str]] = []
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, payload in methods.items():
            if not isinstance(payload, dict):
                continue
            operations.append((str(path), str(method).upper()))

    if not operations:
        raise SystemExit("OpenAPI specification does not expose any operations")

    method_counts = Counter(method for _, method in operations)
    summary = {
        "spec_path": str(spec_path),
        "version": version,
        "paths": len(paths),
        "operations": len(operations),
        "methods": dict(sorted(method_counts.items())),
    }
    json.dump(summary, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    main()
