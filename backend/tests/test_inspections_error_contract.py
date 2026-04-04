from __future__ import annotations

from app.api.routes.inspections import _inspection_bad_request


def test_inspection_bad_request_has_structured_error_detail() -> None:
    exc = _inspection_bad_request("invalid inspection payload")

    assert exc.status_code == 400
    assert exc.detail["code"] == "INSPECTION_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "INSPECTION_VALIDATION_ERROR"
    assert exc.detail["message"] == "invalid inspection payload"
