from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_pilot_readiness_generates_reports(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    cmd = [sys.executable, "scripts/pilot_readiness.py"]
    result = subprocess.run(cmd, cwd=repo, check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)
    assert payload["status"] in {"ready", "not_ready"}

    assert (repo / "docs" / "pilot" / "pilot_readiness_report.json").exists()
    assert (repo / "docs" / "PILOT_GO_LIVE_REPORT.md").exists()


def test_bootstrap_runbook_exists() -> None:
    repo = Path(__file__).resolve().parents[3]
    assert (repo / "docs" / "TENANT_BOOTSTRAP_RUNBOOK.md").exists()
