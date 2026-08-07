"""Pin test for RB-002f-B — perf-smoke dashboard flow has login + summary steps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FLOW_FILE = ROOT / "scripts" / "perf" / "flows" / "dashboard_summary.json"


@pytest.fixture(scope="module")
def flow() -> list[dict]:
    return json.loads(FLOW_FILE.read_text(encoding="utf-8"))


def test_flow_has_exactly_two_steps(flow: list[dict]) -> None:
    assert len(flow) == 2, f"expected exactly 2 steps (login + summary), got {len(flow)}"


def test_step_0_is_auth_login_post(flow: list[dict]) -> None:
    step = flow[0]
    assert step["method"].upper() == "POST"
    assert step["path"] == "/api/v1/auth/login"
    assert step.get("expect_status", 200) == 200
    body = step.get("body", {})
    assert "email" in body and "password" in body, "login step must POST email+password"


def test_step_0_captures_access_token(flow: list[dict]) -> None:
    capture = flow[0].get("capture", {})
    assert (
        "access_token" in capture
    ), "step 0 must capture the bearer token under key 'access_token'"
    assert capture["access_token"] == "access_token", (
        "capture must read 'access_token' from the login response body "
        "(top-level field per backend/app/api/routes/auth.py TokenPair); "
        "changing this path silently breaks the bearer in step 1"
    )


def test_step_1_is_dashboard_summary_with_bearer(flow: list[dict]) -> None:
    step = flow[1]
    assert step["method"].upper() == "GET"
    assert step["path"] == "/api/v1/dashboard/summary"
    auth_header = step.get("headers", {}).get("Authorization", "")
    assert (
        auth_header == "Bearer {{access_token}}"
    ), "step 1 must use the captured token in the Authorization header"
