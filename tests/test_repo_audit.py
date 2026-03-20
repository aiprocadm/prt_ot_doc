from __future__ import annotations

import json
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
