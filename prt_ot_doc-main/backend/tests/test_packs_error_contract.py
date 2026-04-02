import pytest
from fastapi import HTTPException, status

from app.api.routes.packs import _pack_bad_request, _validate_pack_output_selection


def test_pack_bad_request_returns_structured_detail() -> None:
    exc = _pack_bad_request("Site does not belong to company")

    assert isinstance(exc, HTTPException)
    assert exc.status_code == status.HTTP_400_BAD_REQUEST
    assert exc.detail == {
        "code": "pack_validation_error",
        "message": "Site does not belong to company",
    }


def test_validate_pack_output_selection_raises_structured_bad_request() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _validate_pack_output_selection(False, False)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == {
        "code": "pack_validation_error",
        "message": "At least one of include_docx or include_pdf must be enabled",
    }


def test_validate_pack_output_selection_accepts_any_enabled_output() -> None:
    _validate_pack_output_selection(True, False)
    _validate_pack_output_selection(False, True)
