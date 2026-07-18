"""Pin tests for the ``scripts/perf/scenarios.json`` nightly_baseline trim.

Closes the RB-002 caveat ("FLOW perf scenarios reference demo entities
not seeded by bootstrap_demo_tenant"). The nightly_baseline profile is
trimmed to pure-GET scenarios only — FLOW probes were removed because
they referenced literal entity IDs (`demo-company`, `demo-person`,
`demo-document-version-id`, `Greeting`/`TMP` template codes) that
bootstrap creates with auto-generated UUIDs.

These tests are the invariant guard: any future addition of a FLOW
scenario (or any non-GET method) to nightly_baseline must come with
a matching update to bootstrap_demo_tenant — otherwise CI will fail
with un-resolvable POST bodies as it did before this trim.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIOS_PATH = _REPO_ROOT / "scripts" / "perf" / "scenarios.json"


def _load() -> dict:
    return json.loads(_SCENARIOS_PATH.read_text(encoding="utf-8"))


def test_scenarios_json_is_valid_and_has_both_profiles() -> None:
    data = _load()
    assert "profiles" in data
    assert "pr_smoke" in data["profiles"]
    assert "nightly_baseline" in data["profiles"]
    assert isinstance(data["profiles"]["pr_smoke"], list)
    assert isinstance(data["profiles"]["nightly_baseline"], list)


def test_nightly_baseline_is_pure_get_only() -> None:
    """All nightly_baseline scenarios must be pure GETs (no ``method`` field
    or ``method == "GET"``). FLOW / POST scenarios break against the
    demo seed (literal entity IDs vs. auto-UUID bootstrap).
    """
    data = _load()
    for scenario in data["profiles"]["nightly_baseline"]:
        method = scenario.get("method", "GET")
        assert method == "GET", (
            f"nightly_baseline scenario {scenario.get('name')!r} has "
            f"method={method!r} — must be GET-only until bootstrap_demo_tenant "
            f"seeds the entities it references. See "
            f"docs/stabilization/perf-baseline.md (Trim section)."
        )


def test_nightly_baseline_has_no_flow_steps() -> None:
    """Defense-in-depth: even a GET-method scenario must not have flow_steps
    declared (which would make it a multi-step probe regardless of method).
    """
    data = _load()
    for scenario in data["profiles"]["nightly_baseline"]:
        assert "flow_steps" not in scenario, (
            f"nightly_baseline scenario {scenario.get('name')!r} has "
            f"flow_steps — pure-GET trim violated."
        )


def test_nightly_baseline_no_banned_flow_scenario_names() -> None:
    """Hard pin against the 3 specific scenarios removed by the 2026-05-29
    trim. Re-adding any of them by name (even if reshaped to GET) needs a
    deliberate review of the bootstrap seed strategy.
    """
    data = _load()
    names = {scenario.get("name") for scenario in data["profiles"]["nightly_baseline"]}
    banned = {
        "document_generate_apply_headers",
        "files_upload_flow",
        "jobs_status_transitions",
    }
    overlap = names & banned
    assert not overlap, (
        f"nightly_baseline contains banned FLOW scenario(s): {sorted(overlap)}. "
        f"These were removed because they reference literal entity IDs "
        f"(demo-company, demo-person, demo-document-version-id, "
        f"template_code=Greeting/TMP) that bootstrap_demo_tenant does not "
        f"seed. Either extend bootstrap to seed them or use parameterized "
        f"discovery — see docs/stabilization/perf-baseline.md."
    )


def test_pr_smoke_profile_untouched_by_trim() -> None:
    """pr_smoke is the blocking gate; the trim is for nightly_baseline only.
    Pin pr_smoke shape to catch accidental scope-creep of the trim.
    """
    data = _load()
    pr_smoke_names = [s.get("name") for s in data["profiles"]["pr_smoke"]]
    expected = ["health", "dashboard", "templates_list", "search_suggest"]
    assert pr_smoke_names == expected, (
        f"pr_smoke shape changed: expected {expected}, got {pr_smoke_names}"
    )


def test_nightly_baseline_has_expected_pure_get_set() -> None:
    """After the trim, nightly_baseline contains exactly the 5 GET probes."""
    data = _load()
    names = [s.get("name") for s in data["profiles"]["nightly_baseline"]]
    expected = ["health", "dashboard", "templates_list", "search_suggest", "download_file"]
    assert names == expected, (
        f"nightly_baseline shape unexpected: expected {expected}, got {names}"
    )


def test_dataset_assumptions_notes_documents_the_trim() -> None:
    """The notes string must reference the RB-002 trim rationale so future
    readers can find the explanation. Lightweight discoverability check.
    """
    data = _load()
    notes = data.get("dataset_assumptions", {}).get("notes", "")
    assert "RB-002" in notes or "pure-GET" in notes, (
        f"dataset_assumptions.notes missing RB-002 / pure-GET reference: "
        f"{notes!r}"
    )
