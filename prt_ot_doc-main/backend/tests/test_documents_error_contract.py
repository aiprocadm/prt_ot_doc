from types import SimpleNamespace

import pytest
from fastapi import HTTPException, status

from app.api.routes.documents import _fetch_template, _serialize_payload


def test_serialize_payload_raises_structured_bad_request_for_non_serializable_data() -> None:
    with pytest.raises(HTTPException) as exc_info:
        _serialize_payload({"value": {1, 2, 3}})

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == {
        "code": "documents_bad_request",
        "message": "data must be JSON serializable",
    }


@pytest.mark.asyncio
async def test_fetch_template_requires_template_code_with_structured_bad_request() -> None:
    tenant = SimpleNamespace(slug="tenant-a")

    with pytest.raises(HTTPException) as exc_info:
        await _fetch_template(
            session=None,
            tenant=tenant,
            template_code=None,
            template_id=None,
            template_version=1,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == {
        "code": "documents_bad_request",
        "message": "template_code is required for template selection",
    }


@pytest.mark.asyncio
async def test_fetch_template_requires_template_version_with_structured_bad_request() -> None:
    tenant = SimpleNamespace(slug="tenant-a")

    with pytest.raises(HTTPException) as exc_info:
        await _fetch_template(
            session=None,
            tenant=tenant,
            template_code="tmpl",
            template_id=None,
            template_version=None,
        )

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == {
        "code": "documents_bad_request",
        "message": "template_version is required for template selection",
    }
