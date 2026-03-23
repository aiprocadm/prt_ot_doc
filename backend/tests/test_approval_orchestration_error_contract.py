from fastapi import HTTPException, status

from app.api.routes.approval_orchestration import _approval_orchestration_unprocessable


def test_approval_orchestration_unprocessable_returns_structured_detail() -> None:
    exc = _approval_orchestration_unprocessable("request_id required")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.detail == {
        "code": "approval_orchestration_validation_error",
        "message": "request_id required",
    }
