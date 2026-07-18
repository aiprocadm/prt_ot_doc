from __future__ import annotations

from app.api.routes.persons import _person_bad_request, _person_unprocessable


def test_persons_bad_request_has_structured_error_detail() -> None:
    exc = _person_bad_request("position mismatch")

    assert exc.status_code == 400
    assert exc.detail["code"] == "PERSON_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "PERSON_VALIDATION_ERROR"
    assert exc.detail["message"] == "position mismatch"


def test_persons_unprocessable_has_structured_error_detail() -> None:
    exc = _person_unprocessable("first_name cannot be empty")

    assert exc.status_code == 422
    assert exc.detail["code"] == "PERSON_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "PERSON_VALIDATION_ERROR"
    assert exc.detail["message"] == "first_name cannot be empty"
