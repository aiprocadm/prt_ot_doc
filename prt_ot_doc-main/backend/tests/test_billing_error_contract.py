from fastapi import HTTPException, status

from app.api.routes.billing import _billing_bad_request


def test_billing_bad_request_returns_structured_detail() -> None:
    exc = _billing_bad_request("IDEMPOTENCY_REQUIRED", "Idempotency-Key required")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == {
        "code": "IDEMPOTENCY_REQUIRED",
        "message": "Idempotency-Key required",
    }
