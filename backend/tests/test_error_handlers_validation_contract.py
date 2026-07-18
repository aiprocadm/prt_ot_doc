"""Regression contract for the request-validation exception handler.

Pydantic v2 embeds the *raw* exception object raised by a validator under
``exc.errors()[i]["ctx"]["error"]``. The unified handler in
:mod:`app.api.error_handlers` used to pass ``exc.errors()`` straight into
:class:`fastapi.responses.JSONResponse`, so that ``ValueError`` object hit the
JSON encoder and raised ``TypeError: Object of type ValueError is not JSON
serializable`` — turning a clean ``422`` into a ``500``.

These tests drive the *real* production handler (registered via
:func:`register_exception_handlers`) through the real HTTP stack, using a tiny
local model that reproduces the exact same ``ctx.error`` shape as
``DocGenerateRequest._ensure_identifier``. They are intentionally hermetic (no
DB / auth / ``python-magic`` imports) so they run anywhere, unlike anything that
imports ``app.api.routes.documents`` on Windows + Py3.13.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, status
from fastapi.testclient import TestClient
from pydantic import BaseModel, model_validator

from app.api.error_handlers import register_exception_handlers


class _IdentifierModel(BaseModel):
    """Mirrors DocGenerateRequest: an after-validator that raises ValueError."""

    template_code: str | None = None
    data: dict[str, Any] = {}

    @model_validator(mode="after")
    def _ensure_identifier(self) -> "_IdentifierModel":
        if not self.template_code:
            raise ValueError("template_code is required to select a template")
        return self


def _make_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/probe/identifier")
    def _probe(body: _IdentifierModel):  # pragma: no cover - exercised via client
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_validator_value_error_yields_clean_422_with_json_body() -> None:
    """A validator-raised ValueError must serialize to a clean 422, not crash to 500."""
    client = _make_client()

    resp = client.post("/probe/identifier", json={"data": {}})

    # Before the fix this was 500 (encoder TypeError); contract is 422.
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text

    payload = resp.json()  # must be valid JSON — a crash would not round-trip
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["type"] == "validation"

    # The embedded ValueError is stringified (not dropped) so the message survives.
    embedded = payload["details"]["errors"][0]["ctx"]["error"]
    assert isinstance(embedded, str)
    assert "template_code is required to select a template" in embedded


def test_standard_field_validation_still_returns_clean_422() -> None:
    """Coercing ctx must not regress the ordinary (no ctx.error) validation path."""
    client = _make_client()

    # Wrong type for ``data`` → built-in validation error with no ctx.error object.
    resp = client.post("/probe/identifier", json={"template_code": "x", "data": "not-a-dict"})

    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY, resp.text
    payload = resp.json()
    assert payload["code"] == "VALIDATION_ERROR"
    assert payload["field_errors"], "field_errors should be populated for type errors"
