from __future__ import annotations

import pytest
from fastapi import HTTPException, Response
from pydantic import BaseModel

from app.models.models import IdempotencyStatus
from app.services.idempotency import IdempotencyService, normalize_idempotency_key


class _PayloadModel(BaseModel):
    ok: bool


class _ErrorModel(BaseModel):
    detail: str


@pytest.mark.parametrize(
    "value, expected",
    [
        (" key ", "key"),
        ("abc", "abc"),
    ],
)
def test_normalize_idempotency_key_valid(value: str, expected: str) -> None:
    assert normalize_idempotency_key(value) == expected


@pytest.mark.parametrize("value", [None, "   ", "x" * 129])
def test_normalize_idempotency_key_invalid(value: str | None) -> None:
    with pytest.raises(HTTPException):
        normalize_idempotency_key(value)


@pytest.mark.anyio()
async def test_acquire_creates_and_reuses_records(sessionmaker) -> None:
    async with sessionmaker() as session:
        service = IdempotencyService(session=session, tenant_id="tenant", endpoint="demo")
        record, created = await service.acquire(
            key="abc",
            request_hash="hash-1",
            method="POST",
            path="/demo",
        )
        assert created is True
        assert record.status is IdempotencyStatus.PENDING

        await service.store_success(record, status_code=200, body={"ok": True})

        reused, reused_created = await service.acquire(
            key="abc",
            request_hash="hash-1",
            method="POST",
            path="/demo",
        )
        assert reused_created is False
        assert reused.request_hash == "hash-1"
        assert reused.method == "POST"
        assert reused.path == "/demo"

        await session.rollback()


@pytest.mark.anyio()
async def test_acquire_detects_conflicting_hash(sessionmaker) -> None:
    async with sessionmaker() as session:
        service = IdempotencyService(session=session, tenant_id="tenant", endpoint="demo")
        await service.acquire(key="abc", request_hash="hash-1")
        with pytest.raises(HTTPException) as excinfo:
            await service.acquire(key="abc", request_hash="hash-2")
        assert excinfo.value.status_code == 409


@pytest.mark.anyio()
async def test_store_success_and_response(sessionmaker) -> None:
    async with sessionmaker() as session:
        service = IdempotencyService(session=session, tenant_id="tenant", endpoint="demo")
        record, _ = await service.acquire(key="abc")
        await service.store_success(record, status_code=201, body={"ok": True})
        await session.flush()

        stored = await service.get(key="abc")
        assert stored is not None
        assert stored.status is IdempotencyStatus.SUCCEEDED
        assert stored.result_json["status_code"] == 201

        response = Response()
        payload = await service.respond_from_store(stored, model=_PayloadModel, response=response)
        assert payload.ok is True
        assert response.status_code == 201


@pytest.mark.anyio()
async def test_store_failure_handles_models(sessionmaker) -> None:
    async with sessionmaker() as session:
        service = IdempotencyService(session=session, tenant_id="tenant", endpoint="demo")
        record, _ = await service.acquire(key="xyz")
        await service.store_failure(record, status_code=422, detail=_ErrorModel(detail="boom"))
        await session.flush()

        stored = await service.get(key="xyz")
        assert stored is not None
        assert stored.status is IdempotencyStatus.FAILED
        assert stored.result_json["status_code"] == 422
        with pytest.raises(HTTPException) as excinfo:
            await service.respond_from_store(stored, model=_PayloadModel)
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail == "boom"


@pytest.mark.anyio()
async def test_respond_from_store_handles_non_json_body(sessionmaker) -> None:
    async with sessionmaker() as session:
        service = IdempotencyService(session=session, tenant_id="tenant", endpoint="demo")
        record, _ = await service.acquire(key="raw")
        record.status = IdempotencyStatus.FAILED
        record.status_code = 500
        record.response_body = "internal error"
        await session.flush()

        with pytest.raises(HTTPException) as excinfo:
            await service.respond_from_store(record, model=_PayloadModel)
        assert excinfo.value.status_code == 500
        assert excinfo.value.detail == "internal error"
