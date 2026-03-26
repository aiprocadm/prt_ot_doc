import pytest
from fastapi import HTTPException, status

from app.api.routes.approval_signing_v1 import (
    _require_document_object_id,
    _validate_certificate_period,
)


def test_require_document_object_id_raises_structured_unprocessable() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _require_document_object_id(None, None)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == {
        "code": "approval_signing_validation_error",
        "message": "document_version_id is required",
    }


def test_validate_certificate_period_raises_structured_unprocessable() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_certificate_period({"valid_from": "2026-12-31", "valid_to": "2026-01-01"})

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == {
        "code": "approval_signing_validation_error",
        "message": "invalid certificate period",
    }


def test_require_document_object_id_prefers_explicit_object_id() -> None:
    assert _require_document_object_id("doc-1", "obj-1") == "obj-1"
