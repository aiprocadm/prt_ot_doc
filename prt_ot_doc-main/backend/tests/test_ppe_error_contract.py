from __future__ import annotations

from app.api.routes.ppe import _ppe_bad_request


def test_ppe_bad_request_has_structured_error_detail() -> None:
    exc = _ppe_bad_request("invalid ppe payload")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "ppe_validation_error",
        "message": "invalid ppe payload",
    }
