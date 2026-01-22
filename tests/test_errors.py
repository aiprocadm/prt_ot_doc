import pytest
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.api.error_handlers import TRACE_HEADER, register_exception_handlers


@pytest.fixture()
def app_with_handlers() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/items")
    async def create_item(payload: dict[str, int]) -> dict[str, int]:
        return payload

    @app.get("/forbidden")
    async def forbidden() -> None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected")

    return app


@pytest.mark.anyio
async def test_validation_error_uses_unified_payload(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post("/items", json={"value": "not-an-int"})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert isinstance(body["details"].get("errors"), list)
    assert response.headers[TRACE_HEADER] == body["trace_id"]


@pytest.mark.anyio
async def test_forbidden_error_uses_unified_payload(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/forbidden")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    body = response.json()
    assert body["code"] == "forbidden"
    assert body["message"] == "Access denied"
    assert body["details"] == {}
    assert body["trace_id"]
    assert response.headers[TRACE_HEADER] == body["trace_id"]


@pytest.mark.anyio
async def test_internal_error_uses_unified_payload(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    body = response.json()
    assert body["code"] == "internal"
    assert body["message"] == "Internal Server Error"
    assert body["details"] == {}
    assert body["trace_id"]
    assert response.headers[TRACE_HEADER] == body["trace_id"]


@pytest.mark.anyio
async def test_not_found_error_uses_unified_payload(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/missing")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    body = response.json()
    assert body["code"] == "not_found"
    assert body["message"] == "Not Found"
    assert body["details"] == {}
    assert body["trace_id"]
    assert response.headers[TRACE_HEADER] == body["trace_id"]
