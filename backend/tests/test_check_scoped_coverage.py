"""Unit tests for the scoped coverage gate (TZ-6.3-V11-01). App-free.

Exercises the pure ``evaluate`` core with synthetic coverage.json dicts so the
gate logic is verified deterministically without a real (CI-only) coverage run.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_scoped_coverage.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_scoped_coverage", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


# core 60/100 line, 10/20 branch; domain 45/50 line, 8/10 branch;
# services 40/200 line, 8/40 branch; api file is OUT of every scope.
_COVERAGE = {
    "files": {
        "backend/app/core/security.py": {
            "summary": {
                "num_statements": 100,
                "covered_lines": 60,
                "num_branches": 20,
                "covered_branches": 10,
            }
        },
        "backend/app/domains/risk/calc.py": {
            "summary": {
                "num_statements": 50,
                "covered_lines": 45,
                "num_branches": 10,
                "covered_branches": 8,
            }
        },
        "backend/app/services/outbox.py": {
            "summary": {
                "num_statements": 200,
                "covered_lines": 40,
                "num_branches": 40,
                "covered_branches": 8,
            }
        },
        "backend/app/api/routes/ppe.py": {
            "summary": {
                "num_statements": 999,
                "covered_lines": 0,
                "num_branches": 0,
                "covered_branches": 0,
            }
        },
    }
}

_BASELINE = {
    "target_line_percent": 85.0,
    "scopes": {
        "core": {
            "floor_line_percent": 45.0,
            "floor_branch_percent": 30.0,
            "patterns": ["backend/app/core/"],
        },
        "domain": {
            "floor_line_percent": 40.0,
            "floor_branch_percent": 25.0,
            "patterns": ["backend/app/domains/"],
        },
        "services": {
            "floor_line_percent": 25.0,
            "floor_branch_percent": 20.0,
            "patterns": ["backend/app/services/"],
        },
    },
}


def test_collect_scope_stats_sums_matching_files_only():
    mod = _load()
    line, branch, statements, branches = mod.collect_scope_stats(_COVERAGE, ["backend/app/core/"])
    assert statements == 100  # the api/routes file is excluded
    assert line == 60.0
    assert branch == 50.0


def test_evaluate_computes_per_scope_line_and_target_gap():
    mod = _load()
    result = mod.evaluate(_COVERAGE, _BASELINE, target=85.0)
    scopes = result["scopes"]
    assert scopes["core"]["line"] == 60.0
    assert scopes["core"]["gap_to_target"] == 25.0  # 85 - 60
    assert scopes["core"]["target_met"] is False
    assert scopes["domain"]["line"] == 90.0
    assert scopes["domain"]["target_met"] is True  # 90 >= 85
    assert scopes["domain"]["gap_to_target"] == 0.0
    assert scopes["services"]["line"] == 20.0


def test_evaluate_flags_regression_below_floor():
    mod = _load()
    result = mod.evaluate(_COVERAGE, _BASELINE, target=85.0)
    # services line 20% < floor 25% -> regressed
    assert result["scopes"]["services"]["regressed"] is True
    assert any("services" in e for e in result["errors"])
    # core/domain above their floors -> not regressed
    assert result["scopes"]["core"]["regressed"] is False
    assert result["scopes"]["domain"]["regressed"] is False


def test_evaluate_passes_when_all_above_floor():
    mod = _load()
    baseline = {
        "target_line_percent": 85.0,
        "scopes": {
            "services": {
                "floor_line_percent": 10.0,
                "floor_branch_percent": 10.0,
                "patterns": ["backend/app/services/"],
            },
        },
    }
    result = mod.evaluate(_COVERAGE, baseline, target=85.0)
    assert result["errors"] == []
    assert result["scopes"]["services"]["regressed"] is False


def test_main_returns_1_on_regression(tmp_path):
    mod = _load()
    cov = tmp_path / "coverage.json"
    base = tmp_path / "baseline.json"
    cov.write_text(json.dumps(_COVERAGE), encoding="utf-8")
    base.write_text(json.dumps(_BASELINE), encoding="utf-8")
    rc = mod.main(["--coverage-json", str(cov), "--baseline", str(base)])
    assert rc == 1  # services regressed below floor


def test_main_returns_0_when_clean(tmp_path):
    mod = _load()
    cov = tmp_path / "coverage.json"
    base = tmp_path / "baseline.json"
    cov.write_text(json.dumps(_COVERAGE), encoding="utf-8")
    base.write_text(
        json.dumps(
            {
                "target_line_percent": 85.0,
                "scopes": {
                    "core": {
                        "floor_line_percent": 10.0,
                        "floor_branch_percent": 10.0,
                        "patterns": ["backend/app/core/"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    rc = mod.main(["--coverage-json", str(cov), "--baseline", str(base)])
    assert rc == 0
