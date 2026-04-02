from __future__ import annotations

from app.api.routes.persons import _person_bad_request, _person_unprocessable


def test_persons_bad_request_has_structured_error_detail() -> None:
    exc = _person_bad_request("position mismatch")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "person_validation_error",
        "message": "position mismatch",
    }


def test_persons_unprocessable_has_structured_error_detail() -> None:
    exc = _person_unprocessable("first_name cannot be empty")

    assert exc.status_code == 422
    assert exc.detail == {
        "code": "person_validation_error",
        "message": "first_name cannot be empty",
    }
