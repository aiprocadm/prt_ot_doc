#!/usr/bin/env python3
"""Scoped coverage gate for core/domain/services (TZ-6.3-V11-01).

Complements ``scripts/ci/check_backend_coverage_baseline.py`` (whole-app
ratchet) with a *scoped* climb tracker: it enforces a per-scope ratchet floor
AND reports each scope's gap to the 85% North-Star target documented in
``docs/stabilization/coverage_climb_plan.md``.

The gate is a ratchet (fail on regression below the recorded floor), NOT a hard
85% gate — the current baseline (~47% overall, 2026-04-19) is far below 85%, so
a hard gate would block every build. 85% is the documented destination; the
floor climbs toward it over time as tests are added.

Pure-core design: :func:`evaluate` takes plain dicts (coverage.json + baseline)
and returns a structured verdict with zero I/O, so the gate logic is unit-tested
deterministically without a real (CI-only) coverage run.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 100.0
    return (numerator / denominator) * 100.0


def collect_scope_stats(
    coverage: dict[str, Any], patterns: list[str]
) -> tuple[float, float, int, int]:
    """Aggregate line/branch coverage across coverage.json files matching any of
    ``patterns`` (exact or prefix match), one scope at a time. Mirrors the
    whole-app baseline script's collector."""
    files = coverage.get("files", {})
    statements = covered_lines = branches = covered_branches = 0
    for file_path, file_data in files.items():
        if not any(file_path == p or file_path.startswith(p) for p in patterns):
            continue
        summary = file_data.get("summary", {})
        statements += int(summary.get("num_statements", 0))
        covered_lines += int(summary.get("covered_lines", 0))
        branches += int(summary.get("num_branches", 0))
        covered_branches += int(summary.get("covered_branches", 0))
    return (
        pct(covered_lines, statements),
        pct(covered_branches, branches),
        statements,
        branches,
    )


def evaluate(
    coverage: dict[str, Any], baseline: dict[str, Any], target: float = 85.0
) -> dict[str, Any]:
    """Compute per-scope coverage, ratchet regressions, and gap-to-target.

    Returns ``{"target", "scopes": {name: {...}}, "errors": [...]}``. A scope is
    ``regressed`` when its line or branch coverage drops below the recorded
    floor; ``errors`` lists every regression (non-empty => the gate fails).
    """
    target = float(baseline.get("target_line_percent", target))
    scopes: dict[str, Any] = {}
    errors: list[str] = []

    for name, cfg in baseline.get("scopes", {}).items():
        patterns = list(cfg.get("patterns", []))
        floor_line = float(cfg.get("floor_line_percent", 0.0))
        floor_branch = float(cfg.get("floor_branch_percent", 0.0))
        line, branch, statements, branches = collect_scope_stats(coverage, patterns)

        regressed = False
        if line < floor_line:
            errors.append(f"{name} line coverage {line:.2f}% is below floor {floor_line:.2f}%")
            regressed = True
        if branch < floor_branch:
            errors.append(
                f"{name} branch coverage {branch:.2f}% is below floor {floor_branch:.2f}%"
            )
            regressed = True

        scopes[name] = {
            "line": line,
            "branch": branch,
            "statements": statements,
            "branches": branches,
            "floor_line": floor_line,
            "floor_branch": floor_branch,
            "target_met": line >= target,
            "gap_to_target": max(0.0, round(target - line, 2)),
            "regressed": regressed,
        }

    return {"target": target, "scopes": scopes, "errors": errors}


def _format_report(result: dict[str, Any]) -> str:
    out = [f"[scoped-coverage] North-Star target = {result['target']:.2f}% line"]
    for name, s in result["scopes"].items():
        if s["regressed"]:
            flag = "REGRESSED"
        elif s["target_met"]:
            flag = "TARGET MET"
        else:
            flag = f"climbing (+{s['gap_to_target']:.2f}% to target)"
        out.append(
            f"[scoped-coverage] {name}: line={s['line']:.2f}% (floor {s['floor_line']:.2f}%), "
            f"branch={s['branch']:.2f}% (floor {s['floor_branch']:.2f}%), "
            f"statements={s['statements']} — {flag}"
        )
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scoped coverage ratchet + 85% North-Star tracker (core/domain/services)."
    )
    parser.add_argument("--coverage-json", default="artifacts/coverage.json")
    parser.add_argument("--baseline", default="docs/stabilization/scoped_coverage_baseline.json")
    parser.add_argument("--target", type=float, default=85.0)
    args = parser.parse_args(argv)

    coverage = json.loads(Path(args.coverage_json).read_text(encoding="utf-8"))
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))

    result = evaluate(coverage, baseline, target=args.target)
    print(_format_report(result))

    if result["errors"]:
        print("\nScoped coverage regression detected:")
        for error in result["errors"]:
            print(f" - {error}")
        return 1

    print("\nScoped coverage ratchet passed (no regression below floor).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
