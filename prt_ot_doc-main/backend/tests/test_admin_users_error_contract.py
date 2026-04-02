import pytest
from fastapi import HTTPException, status

from app.api.routes.admin_users import _admin_user_unprocessable, _normalize_roles


def test_admin_user_unprocessable_returns_structured_detail() -> None:
    exc = _admin_user_unprocessable("At least one role is required")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc.detail == {
        "code": "admin_user_validation_error",
        "message": "At least one role is required",
    }


def test_normalize_roles_raises_structured_detail_for_unsupported_role() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _normalize_roles(["not-a-role"])

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == {
        "code": "admin_user_validation_error",
        "message": "Unsupported role: not-a-role",
    }
