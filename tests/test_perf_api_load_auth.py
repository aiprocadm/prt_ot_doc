"""iter-27 RB-002 perf-auth pin tests for ``scripts/perf/api_load.py``.

Why these tests exist:

* Memory `mvp-release-blockers` notes that **RB-002** was repeatedly held open
  because perf-baseline scenarios returning 401 looked identical to the
  earlier `relation "tenant" does not exist` failure mode — both surface as
  ``Unexpected response statuses [...], expected [200]``. These tests pin the
  *new* auth plumbing so a future regression on ``--login-email`` / ``--access-token``
  semantics fails *here*, not deep inside a CI workflow log.
* `dashboard_summary.json` (the iter-18 flow-step approach for **perf-smoke**)
  re-logs in on every worker — that's fine for 60 requests but doubles latency
  measurements. **iter-27** introduces a one-shot global token; these tests
  pin the cheaper path so it doesn't silently revert to the older pattern.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

# Implicit namespace package — pyproject.toml::pythonpath includes ".".
api_load = importlib.import_module("scripts.perf.api_load")


REPO_ROOT = Path(__file__).resolve().parents[1]
API_LOAD_SCRIPT = REPO_ROOT / "scripts" / "perf" / "api_load.py"


# ---------------------------------------------------------------------------
# CLI parser guards (mutual exclusion, required-together)
# ---------------------------------------------------------------------------


def _run_cli(*extra_args: str) -> subprocess.CompletedProcess[str]:
    """Spawn the script with the given extra args and capture stderr.

    We use ``subprocess`` not ``parser.parse_args`` because ``argparse.error``
    calls ``sys.exit`` which is hard to assert against cleanly across pytest
    versions; the spawned process exits with code 2 and writes the message.
    """

    return subprocess.run(
        [sys.executable, str(API_LOAD_SCRIPT), *extra_args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_rejects_token_and_login_together() -> None:
    result = _run_cli(
        "--access-token", "jwt-x",
        "--login-email", "a@example.com",
        "--login-password", "p",
    )
    assert result.returncode == 2, result.stderr
    assert "mutually exclusive" in result.stderr


def test_cli_requires_login_email_and_password_together() -> None:
    result = _run_cli("--login-email", "a@example.com")
    assert result.returncode == 2, result.stderr
    assert "must be provided together" in result.stderr


def test_cli_accepts_only_login_email_with_password() -> None:
    """Sanity: with valid auth args + a path the parser shouldn't reject — it
    will still fail later when no server is reachable, but parsing must succeed."""

    result = _run_cli(
        "--login-email", "a@example.com",
        "--login-password", "p",
        "--requests", "1",
        "--concurrency", "1",
        "--path", "/health",
        "--base-url", "http://127.0.0.1:1",  # unreachable
    )
    # Parser passes; runtime fails on connect/login.
    assert "mutually exclusive" not in result.stderr
    assert "must be provided together" not in result.stderr


# ---------------------------------------------------------------------------
# _hit Authorization injection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hit_injects_authorization_header_when_token_supplied() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        await api_load._hit(
            client,
            method="GET",
            path="/api/v1/dashboard/summary",
            tenant="demo",
            access_token="jwt-xyz",
        )

    assert captured.get("authorization") == "Bearer jwt-xyz"
    assert captured.get("x-tenant") == "demo"


@pytest.mark.asyncio
async def test_hit_omits_authorization_header_when_no_token() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        await api_load._hit(
            client,
            method="GET",
            path="/health",
            tenant=None,
        )

    assert "authorization" not in captured


@pytest.mark.asyncio
async def test_hit_respects_explicit_authorization_header() -> None:
    """If a caller passes its own Authorization (e.g. a flow_step that captured
    a per-worker token), the global ``access_token`` must NOT override it.
    `_hit` relies on ``dict.setdefault`` for this contract."""

    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(dict(request.headers))
        return httpx.Response(200)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        await api_load._hit(
            client,
            method="GET",
            path="/api/v1/anything",
            tenant=None,
            headers={"Authorization": "Bearer per-step-token"},
            access_token="should-not-win",
        )

    assert captured.get("authorization") == "Bearer per-step-token"


# ---------------------------------------------------------------------------
# _resolve_access_token: login round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_access_token_posts_credentials_and_returns_token() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        assert request.method == "POST"
        assert request.url.path == "/api/v1/auth/login"
        assert request.headers.get("x-tenant") == "demo"
        return httpx.Response(200, json={"access_token": "jwt-from-server"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        token = await api_load._resolve_access_token(
            client,
            login_url="/api/v1/auth/login",
            email="admin@example.com",
            password="hunter2",
            tenant="demo",
        )

    assert token == "jwt-from-server"
    assert len(seen_requests) == 1
    # Body actually carries the credentials (not just the URL).
    body = seen_requests[0].content.decode()
    assert "admin@example.com" in body
    assert "hunter2" in body


@pytest.mark.asyncio
async def test_resolve_access_token_raises_on_non_200() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text='{"detail":"Invalid email or password"}')

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        with pytest.raises(RuntimeError, match="status=401"):
            await api_load._resolve_access_token(
                client,
                login_url="/api/v1/auth/login",
                email="wrong@example.com",
                password="bad",
                tenant="demo",
            )


@pytest.mark.asyncio
async def test_resolve_access_token_raises_when_token_field_missing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        # 200 OK but no access_token — defensive guard for upstream contract drift.
        return httpx.Response(200, json={"unexpected": "shape"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        with pytest.raises(RuntimeError, match="no access_token"):
            await api_load._resolve_access_token(
                client,
                login_url="/api/v1/auth/login",
                email="admin@example.com",
                password="p",
                tenant="demo",
            )


# ---------------------------------------------------------------------------
# _hit_flow integration with global token (setdefault contract)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hit_flow_inherits_global_token_when_step_omits_authorization() -> None:
    seen_auth: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_auth.append(request.headers.get("authorization"))
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://test"
    ) as client:
        await api_load._hit_flow(
            client,
            tenant="demo",
            flow_steps=[
                {"method": "GET", "path": "/api/v1/dashboard/summary", "expect_status": 200},
            ],
            worker_idx=0,
            access_token="global-jwt",
        )

    assert seen_auth == ["Bearer global-jwt"]
