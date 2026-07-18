from __future__ import annotations

from app.api.routes.contracts import _contract_bad_request, _contract_unprocessable


def test_contracts_bad_request_has_structured_error_detail() -> None:
    exc = _contract_bad_request("department mismatch")

    assert exc.status_code == 400
    assert exc.detail == {
        "code": "contract_validation_error",
        "message": "department mismatch",
    }


def test_contracts_unprocessable_has_structured_error_detail() -> None:
    exc = _contract_unprocessable("unsupported contract status")

    assert exc.status_code == 422
    assert exc.detail == {
        "code": "contract_validation_error",
        "message": "unsupported contract status",
    }
