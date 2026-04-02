from __future__ import annotations

from app.api.routes.audit import _audit_bad_request


def test_audit_bad_request_has_structured_error_detail() -> None:
    exc = _audit_bad_request("object_id must not be blank")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "audit_validation_error",
        "message": "object_id must not be blank",
    }
