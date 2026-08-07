"""Simulation honesty guard: fake operator progress is gone from the codebase.

Text-level checks (no route imports — un-collectable on this machine);
HTTP-level honesty is covered by tests/api/.
"""

from __future__ import annotations

from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"


def _src(rel: str) -> str:
    return (APP / rel).read_text(encoding="utf-8")


def test_edo_workflow_router_does_not_schedule_simulation():
    src = _src("api/routes/edo_workflow.py")
    assert "edo_status_simulation_job" not in src
    assert "send_edo_job" not in src
    assert "EDO_PROVIDER_NOT_CONFIGURED" in src


def test_internal_signature_routes_through_pep_core():
    src = _src("api/routes/edo_workflow.py")
    assert "PepSigningService" in src
    assert "SIGNATURE_PROVIDER_NOT_CONFIGURED" in src


def test_simulation_jobs_removed_from_tasks():
    src = _src("tasks/_core.py")
    assert "edo_status_simulation_job" not in src
    assert "def send_edo_job" not in src


def test_mock_providers_removed():
    assert "MockSignatureProvider" not in _src("modules/sign/service.py")
    assert "MockEdoOperator" not in _src("modules/edo/service.py")


def test_orchestration_refresh_is_honest():
    src = _src("api/routes/approval_orchestration.py")
    assert "EDO_PROVIDER_NOT_CONFIGURED" in src
    assert "SIGNATURE_PROVIDER_NOT_CONFIGURED" in src
