from __future__ import annotations

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.core.tenancy import require_tenant


def _request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope = {"type": "http", "method": "GET", "path": "/api/v1/companies", "headers": headers or []}
    return Request(scope)


def test_tenancy_guard_requires_header() -> None:
    req = _request()
    with pytest.raises(HTTPException) as exc:
        require_tenant(req)
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "TENANT_REQUIRED"


def test_tenancy_guard_accepts_slug() -> None:
    req = _request([(b"x-tenant", b"acme")])
    value = require_tenant(req)
    assert value == "acme"
    assert req.state.tenant_slug == "acme"
