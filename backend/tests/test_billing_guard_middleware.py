from __future__ import annotations

from starlette.requests import Request

from app.middleware.billing_guard import resolve_billing_action


def _request(method: str, path: str) -> Request:
    return Request({"type": "http", "method": method, "path": path, "headers": []})


def test_resolve_billing_action_documents_generate() -> None:
    assert (
        resolve_billing_action(_request("POST", "/api/v1/documents:generate"))
        == "documents.generate"
    )


def test_resolve_billing_action_persons_create() -> None:
    assert resolve_billing_action(_request("POST", "/api/v1/persons")) == "persons.create"


def test_resolve_billing_action_default_request() -> None:
    assert resolve_billing_action(_request("GET", "/api/v1/dashboard")) == "request"
