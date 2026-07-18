from __future__ import annotations

from app.api.routes.ppe import _ppe_bad_request


def test_ppe_bad_request_has_structured_error_detail() -> None:
    exc = _ppe_bad_request("invalid ppe payload")

    assert exc.status_code == 400
    assert exc.detail["code"] == "PPE_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "PPE_VALIDATION_ERROR"
    assert exc.detail["message"] == "invalid ppe payload"
