import pytest
from app.api.error_handlers import TRACE_HEADER, register_exception_handlers
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient


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
    assert body["error_code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert body["type"] == "validation"
    assert isinstance(body["details"].get("errors"), list)
    assert body["field_errors"][0]["field"] == "value"
    assert body["field_errors"][0]["message"]
    assert body["correlation_id"] == body["trace_id"]
    assert body["timestamp"]
    assert response.headers[TRACE_HEADER] == body["trace_id"]
    assert response.headers["X-Correlation-Id"] == body["trace_id"]
    assert response.headers["X-Request-Id"] == body["trace_id"]
    assert body["request_id"] == body["trace_id"]


@pytest.mark.anyio
async def test_forbidden_error_uses_unified_payload(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/forbidden")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    body = response.json()
    assert body["code"] == "forbidden"
    assert body["error_code"] == "forbidden"
    assert body["message"] == "Access denied"
    assert body["type"] == "security"
    assert body["details"] == {}
    assert body["field_errors"] == []
    assert body["correlation_id"] == body["trace_id"]
    assert body["timestamp"]
    assert body["trace_id"]
    assert response.headers[TRACE_HEADER] == body["trace_id"]
    assert response.headers["X-Correlation-Id"] == body["trace_id"]
    assert response.headers["X-Request-Id"] == body["trace_id"]
    assert body["request_id"] == body["trace_id"]


@pytest.mark.anyio
async def test_internal_error_uses_unified_payload(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/boom")

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    body = response.json()
    assert body["code"] == "internal"
    assert body["error_code"] == "internal"
    assert body["message"] == "Internal Server Error"
    assert body["type"] == "server"
    assert body["details"] == {}
    assert body["field_errors"] == []
    assert body["correlation_id"] == body["trace_id"]
    assert body["timestamp"]
    assert body["trace_id"]
    assert response.headers[TRACE_HEADER] == body["trace_id"]
    assert response.headers["X-Correlation-Id"] == body["trace_id"]
    assert response.headers["X-Request-Id"] == body["trace_id"]
    assert body["request_id"] == body["trace_id"]


@pytest.mark.anyio
async def test_not_found_error_uses_unified_payload(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get("/missing")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    body = response.json()
    assert body["code"] == "not_found"
    assert body["error_code"] == "not_found"
    assert body["message"] == "Not Found"
    assert body["type"] == "not_found"
    assert body["details"] == {}
    assert body["field_errors"] == []
    assert body["correlation_id"] == body["trace_id"]
    assert body["timestamp"]
    assert body["trace_id"]
    assert response.headers[TRACE_HEADER] == body["trace_id"]
    assert response.headers["X-Correlation-Id"] == body["trace_id"]
    assert response.headers["X-Request-Id"] == body["trace_id"]
    assert body["request_id"] == body["trace_id"]


@pytest.mark.anyio
async def test_error_contract_uses_incoming_correlation_header(app_with_handlers: FastAPI) -> None:
    transport = ASGITransport(app=app_with_handlers, raise_app_exceptions=False)
    correlation_id = "corr-inbound-123"
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.get(
            "/forbidden",
            headers={"X-Correlation-Id": correlation_id},
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    body = response.json()
    assert body["trace_id"] == correlation_id
    assert body["correlation_id"] == correlation_id
    assert body["request_id"] == correlation_id
    assert response.headers[TRACE_HEADER] == correlation_id
    assert response.headers["X-Correlation-Id"] == correlation_id
    assert response.headers["X-Request-Id"] == correlation_id
