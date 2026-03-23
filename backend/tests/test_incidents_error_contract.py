from __future__ import annotations

from app.api.routes.incidents import _incident_bad_request


def test_incident_bad_request_has_structured_error_detail() -> None:
    exc = _incident_bad_request("invalid incident payload")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "incident_validation_error",
        "message": "invalid incident payload",
    }
