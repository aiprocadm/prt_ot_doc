from __future__ import annotations

from pathlib import Path


REQUIRED_RC_DOCS = [
    "ACCEPTANCE_TEST_MATRIX.md",
    "GAP_REPORT.md",
    "RELEASE_READINESS.md",
    "KNOWN_LIMITATIONS.md",
    "docs/audit/TZ_COVERAGE_MATRIX.md",
    "scripts/perf/README.md",
]


def test_required_release_candidate_docs_exist() -> None:
    repo = Path(__file__).resolve().parents[2]
    missing = [path for path in REQUIRED_RC_DOCS if not (repo / path).exists()]
    assert not missing, f"Missing RC docs: {missing}"


def test_acceptance_matrix_references_release_docs() -> None:
    repo = Path(__file__).resolve().parents[2]
    matrix = (repo / "ACCEPTANCE_TEST_MATRIX.md").read_text(encoding="utf-8")
    for marker in ["GAP_REPORT.md", "RELEASE_READINESS.md", "KNOWN_LIMITATIONS.md"]:
        assert marker in matrix
