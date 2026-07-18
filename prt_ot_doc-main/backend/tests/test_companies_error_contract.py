from __future__ import annotations

from app.api.routes.companies import _company_unprocessable


def test_company_unprocessable_has_structured_error_detail() -> None:
    exc = _company_unprocessable("name cannot be empty")

    assert exc.status_code == 422
    assert exc.detail == {
        "code": "company_validation_error",
        "message": "name cannot be empty",
    }
