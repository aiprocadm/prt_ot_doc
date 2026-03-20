from __future__ import annotations

import json
from pathlib import Path

from scripts import repo_audit


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_build_payload_reports_canonical_roots_and_single_frontend_manifest() -> None:
    payload = repo_audit.build_payload()

    assert payload["canonical_roots"]["backend_root"] == "backend"
    assert payload["canonical_roots"]["frontend_root"] == "frontend"
    assert payload["findings"]["active_frontend_manifest_count"] == 1
    assert "frontend/package.json" in payload["inventory"]["package_jsons"]
    assert payload["findings"]["required_docs_present"] == payload["findings"]["required_docs_expected"]


def test_write_outputs_generates_markdown_and_json_snapshots(tmp_path: Path) -> None:
    payload = repo_audit.build_payload()
    markdown = repo_audit.render_markdown(payload)

    assert "# Repository audit snapshot" in markdown
    assert "docs/audit/REPOSITORY_AUDIT.json" in markdown

    repo_audit.write_outputs(payload)

    markdown_path = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.md"
    json_path = REPO_ROOT / "docs/audit/REPOSITORY_AUDIT.json"
    assert markdown_path.exists()
    assert json_path.exists()

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["findings"]["app_compat_shim_present"] is True
    assert any(item["legacy"] == "backend/app/modules/approval" for item in data["legacy_paths"])
import subprocess
import sys
from pathlib import Path


def test_repo_audit_generates_markdown_and_json_snapshots() -> None:
    repo = Path(__file__).resolve().parents[1]

    result = subprocess.run(
        [sys.executable, "scripts/repo_audit.py"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "docs/audit/REPOSITORY_AUDIT.md" in result.stdout
    assert "docs/audit/REPOSITORY_AUDIT.json" in result.stdout

    markdown_report = (repo / "docs/audit/REPOSITORY_AUDIT.md").read_text(encoding="utf-8")
    assert "## Root expectations" in markdown_report
    assert "## Machine-readable artifact" in markdown_report
    assert "frontend/package.json" in markdown_report

    json_report = json.loads((repo / "docs/audit/REPOSITORY_AUDIT.json").read_text(encoding="utf-8"))
    assert json_report["inventory"]["package_jsons"] == ["frontend/package.json"]
    assert any(
        item["path"] == "package.json" and item["status"] == "ok"
        for item in json_report["root_expectations"]
    )
    assert any(
        item["legacy"] == "backend/app/modules/approval"
        and item["canonical"] == "backend/app/modules/approvals"
        for item in json_report["legacy_pairs"]
    )
