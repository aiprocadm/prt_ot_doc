from fastapi import HTTPException, status
import pytest
from starlette.requests import Request

from app.api.routes.replace import _parse_map, _require_tenant


def _request_with_headers(headers: list[tuple[bytes, bytes]]) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/replace/dry-run",
        "headers": headers,
    }
    return Request(scope)


def test_require_tenant_raises_structured_bad_request() -> None:
    request = _request_with_headers([])

    with pytest.raises(HTTPException) as exc_info:
        _require_tenant(request)

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.detail == {
        "code": "replace_bad_request",
        "message": "X-Tenant header is required",
    }


def test_parse_map_raises_structured_unprocessable_for_empty_from() -> None:
    content = b'from,to\n,value\n'

    with pytest.raises(HTTPException) as exc_info:
        _parse_map(content)

    assert exc_info.value.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert exc_info.value.detail == {
        "code": "replace_validation_error",
        "message": "from cannot be empty",
    }
