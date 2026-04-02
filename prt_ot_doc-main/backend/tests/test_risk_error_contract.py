from fastapi import HTTPException, status

from app.api.routes.risk import _risk_bad_request, _risk_unprocessable


def test_risk_unprocessable_returns_structured_detail() -> None:
    exc = _risk_unprocessable("invalid risk_level filter")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.detail == {
        "code": "risk_validation_error",
        "message": "invalid risk_level filter",
    }


def test_risk_bad_request_returns_structured_detail() -> None:
    exc = _risk_bad_request("hazard_code and before are required")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == {
        "code": "risk_bad_request",
        "message": "hazard_code and before are required",
    }
