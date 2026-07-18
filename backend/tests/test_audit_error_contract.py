from __future__ import annotations

from app.api.routes.audit import _audit_bad_request


def test_audit_bad_request_has_structured_error_detail() -> None:
    exc = _audit_bad_request("object_id must not be blank")

    assert exc.status_code == 400
    assert exc.detail["code"] == "AUDIT_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "AUDIT_VALIDATION_ERROR"
    assert exc.detail["message"] == "object_id must not be blank"
