from fastapi import HTTPException, status

from app.api.routes.approval_orchestration import (
    _approval_orchestration_not_found,
    _approval_orchestration_unprocessable,
)


def test_approval_orchestration_unprocessable_returns_structured_detail() -> None:
    exc = _approval_orchestration_unprocessable("request_id required")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.detail["code"] == "APPROVAL_ORCHESTRATION_VALIDATION_ERROR"
    assert exc.detail["error_code"] == "APPROVAL_ORCHESTRATION_VALIDATION_ERROR"
    assert exc.detail["message"] == "request_id required"


def test_approval_orchestration_not_found_returns_structured_detail() -> None:
    exc = _approval_orchestration_not_found("approval_route")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_404_NOT_FOUND
    assert exc.detail["code"] == "APPROVAL_ORCHESTRATION_NOT_FOUND"
    assert exc.detail["error_code"] == "APPROVAL_ORCHESTRATION_NOT_FOUND"
    assert exc.detail["message"] == "approval_route not found"
    assert exc.detail["details"]["resource"] == "approval_route"
