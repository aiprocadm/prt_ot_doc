from __future__ import annotations

from app.api.routes.training import _training_bad_request


def test_training_bad_request_has_structured_error_detail() -> None:
    exc = _training_bad_request("invalid training payload")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "training_validation_error",
        "message": "invalid training payload",
    }
